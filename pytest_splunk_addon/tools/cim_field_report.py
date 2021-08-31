import os.path
import sys
import logging
import json
import argparse
import re
import glob
import time
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from pytest_splunk_addon.helmut.manager.jobs import Jobs
from pytest_splunk_addon.helmut.splunk.cloud import CloudSplunk
from pytest_splunk_addon.standard_lib.addon_parser import AddonParser

from splunklib import binding

logging.basicConfig(
    format='%(asctime)s.%(msecs)03d %(name)s %(levelname)s %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.ERROR)

LOGGER = logging.getLogger('cim-field-report')

def get_gonfig():
    parser = argparse.ArgumentParser(description='Python Script to test Splunk functionality')

    parser.add_argument('--splunk-index', dest='splunk_index', default='*', type=str,
                        help='Splunk index to be used as a source for the report. Default is *')
    parser.add_argument('--splunk-web-scheme', dest='splunk_web_scheme', default='https', type=str, choices=['http', 'https'],
                        help='Splunk connection schema https or http, default is https.')
    parser.add_argument('--splunk-host', dest='splunk_host', default='127.0.0.1', type=str, help='Address of the '
                        'Splunk REST API server host to connect. Default is 127.0.0.1')
    parser.add_argument('--splunk-port', dest='splunk_port', default='8089', type=int,
                        help='Splunk Management port. default is 8089.')
    parser.add_argument('--splunk-user', dest='splunk_user', default='admin', type=str,
                        help='Splunk login user. The user should have search capabilities.')
    parser.add_argument('--splunk-password', dest='splunk_password', type=str, required=True, help='Password of the Splunk user')
    parser.add_argument('--splunk-app', dest='splunk_app', type=str, required=True, help='Path to Splunk app package. The package '
                        'should have the configuration files in the default folder.')
    parser.add_argument('--splunk-report-file', dest='splunk_report_file', default='cim_field_report.json', type=str,
                        help='Output file for cim field report. Default is: cim_field_report.json')
    parser.add_argument('--splunk-max-time', dest='splunk_max_time', default='120', type=int,
                        help='Search query execution time out in seconds. Default is: 120')
    parser.add_argument('--log-level', dest='log_level', default='ERROR', type=str, choices=['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG'],
                        help='Logging level used by the tool')

    args =  parser.parse_args()
    LOGGER.setLevel(args.log_level)

    if not os.path.exists(args.splunk_app) or not os.path.isdir(args.splunk_app):
        msg = 'There is no such directory: {}'.format(args.splunk_app)
        LOGGER.error(msg)
        sys.exit(msg)

    return args


def collect_job_results(job, acc, fn):
    offset, count = 0, 1000
    while True:
        records = job.get_results(offset=offset, count=count).as_list
        LOGGER.debug(f"Read fields: offset: {offset}, count: {count}, found: {len(records)}")
        fn(acc, records)
        offset += count
        if len(records) < count:
            break

    return acc


def get_punct_by_eventtype(jobs, eventtypes, config):
    start = time.time()
    eventtypes_str = ",".join(['"{}"'.format(et) for et in eventtypes])
    query = 'search (index="{}") eventtype IN ({}) | dedup punct,eventtype | table punct,eventtype'.format(config.splunk_index, eventtypes_str)
    LOGGER.debug(query)
    try:
        job = jobs.create(query, auto_finalize_ec=120, max_time=config.splunk_max_time)
        job.wait(config.splunk_max_time)
        LOGGER.debug(job.get_results().as_list)
        result = [(v["eventtype"], v["punct"]) for v in job.get_results().as_list]
        LOGGER.info("Time taken to collect eventtype & punct combinations: {} s".format(time.time()-start))
        return result
    except Exception as e:
        LOGGER.error("Errors when executing search!!! Error: {}".format(e))
        LOGGER.debug(traceback.format_exc())


def get_field_names(jobs, eventtypes, config):
    start = time.time()
    eventtypes_str = ",".join(['"{}"'.format(et) for et in eventtypes])
    query = 'search (index="{}") eventtype IN ({}) | fieldsummary'.format(config.splunk_index, eventtypes_str)
    LOGGER.debug(query)
    try:
        job = jobs.create(query, auto_finalize_ec=120, max_time=config.splunk_max_time)
        job.wait(config.splunk_max_time)
        result = collect_job_results(job, [], lambda acc, recs: acc.extend([v["field"] for v in recs]))
        LOGGER.info("Time taken to collect field names: {} s".format(time.time()-start))
        return result
    except Exception as e:
        LOGGER.error("Errors when executing search!!! Error: {}".format(e))
        LOGGER.debug(traceback.format_exc())


def update_summary(data, records):
    sourcetypes, summary = data
    for entry in records:
        if "sourcetype" in entry:
            sourcetypes.add(entry.pop("sourcetype"))
        
        field_set = frozenset(entry.keys())
        if field_set in summary:
            summary[field_set] += 1
        else:
            summary[field_set] = 1


def get_fieldsummary(jobs, punct_by_eventtype, config):
    start = time.time()
    
    result = {}    
    for eventtype, punct in punct_by_eventtype:
        result[eventtype] = []
        query_templ = 'search (index="{}") eventtype="{}" punct="{}" | fieldsummary'
        query = query_templ.format(config.splunk_index, eventtype, punct.replace("\\", "\\\\").replace('"','\\"'))
        LOGGER.debug(query)
        try:
            job = jobs.create(query, auto_finalize_ec=120, max_time=config.splunk_max_time)
            job.wait(config.splunk_max_time)
            summary = job.get_results().as_list
        except Exception as e:
            LOGGER.error("Errors executing search: {}".format(e))
            LOGGER.debug(traceback.format_exc())


        try:
            for f in summary:
                f["values"] = json.loads(f["values"])
            result[eventtype].append(summary)
        except Exception as e:
            LOGGER.warn('Parameter "values" is not a json object: {}'.format(e))
            LOGGER.debug(traceback.format_exc())

    LOGGER.info("Time taken to build fieldsummary: {}".format(time.time()-start))
    return result


def get_fields_extractions(jobs, eventtypes, fields, config):
    start = time.time()
    report, sourcetypes = {}, set()
    field_list = ",".join(['"{}"'.format(f) for f in fields])
    for eventtype, tags in eventtypes.items():
        query = 'search (index="{}") eventtype="{}" | table sourcetype,{}'.format(config.splunk_index, eventtype, field_list)
        try:
            job = jobs.create(query, auto_finalize_ec=120, max_time=config.splunk_max_time)
            job.wait(config.splunk_max_time)
            et_sourcetypes, et_summary = collect_job_results(job, [set(), {}], update_summary)
            sourcetypes = sourcetypes.union(et_sourcetypes)
            report[eventtype] = {
                "tags": tags,
                "sourcetypes": list(et_sourcetypes),
                "summary": [{"fields": sorted(list(k)), "count": v} for k, v in et_summary.items()]
            }        
        except Exception as e:
            LOGGER.error("Errors when executing search!!! Error: {}".format(e))
            LOGGER.debug(traceback.format_exc())

    LOGGER.info("Time taken to build fields extractions section: {} s".format(time.time()-start))
    return report, sourcetypes


def read_ta_meta(config):
    app_manifest = os.path.join(config.splunk_app, "app.manifest")
    with open(app_manifest) as f:
        manifest = json.load(f)

    ta_id_info = manifest.get("info", {}).get("id", {})
    return {k:v for k,v in ta_id_info.items() if k in ["name", "version"]}


def build_report(jobs, eventtypes, config):
    start = time.time()

    fields = get_field_names(jobs, eventtypes, config)
    if fields:
        extractions, sourcetypes = get_fields_extractions(jobs, eventtypes, fields, config)
    else:
        extractions, sourcetypes = "No field extractions discovered", []

    punct_by_eventtype = get_punct_by_eventtype(jobs, eventtypes, config)
    if punct_by_eventtype:    
        fieldsummary = get_fieldsummary(jobs, punct_by_eventtype, config)
    else:
        fieldsummary = "No punct by eventtype combinations discovered"

    summary = {
        "ta_name": read_ta_meta(config),
        "sourcetypes": list(sourcetypes),
        "extractions": extractions,
        "fieldsummary": fieldsummary
    }

    with open(config.splunk_report_file, "w") as f:
        json.dump(summary, f, indent=4)
    
    LOGGER.info("Total time taken to generate report: {} s".format(time.time()-start))


def get_addon_eventtypes(addon_path):
    parser = AddonParser(addon_path)

    eventtypes = {eventtype: None for eventtype in parser.eventtype_parser.eventtypes.sects}

    stanza_pattern = re.compile("eventtype\s*=\s*(\w+)")
    for stanza, section in parser.tags_parser.tags.sects.items():
        match = stanza_pattern.match(stanza)
        if match and match.groups():
            eventtype = match.groups()[0]
            if eventtype in eventtypes:
                tags = [key for key, option in section.options.items() 
                            if option.value.strip() == "enabled"]
                eventtypes[eventtype] = tags
    
    return eventtypes


def main():
    config = get_gonfig()

    splunk_cfg = {
        "splunkd_scheme": config.splunk_web_scheme,
        "splunkd_host": config.splunk_host,
        "splunkd_port": config.splunk_port,
        "username": config.splunk_user,
        "password": config.splunk_password
    }

    try:
        eventtypes = get_addon_eventtypes(config.splunk_app)

        cloud_splunk = CloudSplunk(**splunk_cfg)
        conn = cloud_splunk.create_logged_in_connector()
        jobs = Jobs(conn)
        
        build_report(jobs, eventtypes, config)

    except (TimeoutError, ConnectionRefusedError) as error:
        msg = 'Failed to connect Splunk instance {}://{}:{}, make sure you provided correct connection information. {}'.format(
            config.splunk_web_scheme, config.splunk_host, config.splunk_port, error)
        LOGGER.error(msg)
        sys.exit(msg)
    except binding.AuthenticationError as error:
        msg = 'Authentication to Splunk instance has failed, make sure you provided correct Splunk credentials. {}'.format(error)
        LOGGER.error(msg)
        sys.exit(msg)
    except Exception as error:
        msg = 'Unexpected exception: {}'.format(error)
        LOGGER.error(msg)
        LOGGER.debug(traceback.format_exc())
        sys.exit(msg)


if __name__ == "__main__":
    main()
