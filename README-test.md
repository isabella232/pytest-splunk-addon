
# Run Addon tests in local environment
## With Kubernetes
### Prerequisitory
- Git
- Python3 (>=3.7)
- kubectl
- jq
- [splunk-operator at cluster-scope](https://splunk.github.io/splunk-operator/Install.html#admin-installation-for-all-namespaces)
```bash
kubectl apply -f ./splunk-operator.yaml
```
### Steps
#### 1. Clone the repository

```bash
git clone git@github.com:splunk/<repo name>.git
cd <repo dir>
```
#### 2. Run Tests

1. Install Requirements
```bash
poetry export --without-hashes --dev -o requirements_dev.txt
pip install -r requirements_dev.txt
# Download only if TEST_TYPE is modinput_functional
curl -s https://api.github.com/repos/splunk/splunk-add-on-for-modinput-test/releases/latest | grep "Splunk_TA.*spl" | grep -v search_head | grep -v indexer | grep -v forwarder | cut -d : -f 2,3 | tr -d \" | wget -qi -;
```

2. Generate addon SPL
 - To generate addon package use `ucc-gen` (output/Splunk_TA_<ADDON_NAME>) and `slim package output/Splunk_TA_<ADDON_NAME>`
 - Replace the extension of generated *.tar.gz to *.spl.
 - Rename the generated .spl with the approriate addon_version from package/default/app.conf id.version i.e. `Splunk_TA_<ADDON_NAME>-<ADDON_VERSION>.spl`

3. Set Variables
```bash
export KUBECONFIG="PATH of Kubernetes Config File"
# If TEST_TYPE is modinput_functional or ui also set the following variable,
export NAMESPACE_NAME="splunk-ta-<ADDON_NAME>"
```
**Note:** If TEST_TYPE is `modinput_functional` or `ui`, also set all variables in [test_credentials.env](test_credentials.env) file with appropriate values encoded with base64.

##### Knowledge

4. Create `src` directory in `tests` of the addon repository and put the SPL generated in step-2 in `tests/src`.

5. Execute Tests
- Default value of `--splunk-version = latest`
```bash
python -m pytest -vv tests/knowledge --splunk-data-generator=<path to pytest-splunk-addon-data.conf file> --splunk-type=kubernetes --splunk-version=<<SPLUNK_VERSION>> --xfail-file=.pytest.expect
```

##### Modinput_Functional / UI

4. Get `namespace.yaml` which will be found at `pytest-splunk-addon/k8s_manifests/splunk_standalone` and put into the root directory of addon repository, also update the value of `NAMESPACE_NAME` in file and apply
```bash
eval "echo \"$(cat ./namespace.yaml)\"" > ./namespace.yaml
kubectl apply -f ./namespace.yaml
```

5. Create secret (this will be used while spinning up the splunk standalone)
```bash
kubectl create secret generic splunk-$NAMESPACE_NAME-secret --from-literal='password=Chang3d!' --from-literal='hec_token=9b741d03-43e9-4164-908b-e09102327d22' -n $NAMESPACE_NAME
```

6. Get `splunk_standalone.yaml` which will be found at `pytest-splunk-addon/k8s_manifests/splunk_standalone` and put into the root directory of addon repository, also update the `SPLUNK_VERSION` in file for which Standalone machine will be created
```bash
eval "echo \"$(cat ./splunk_standalone.yaml)\"" > ./splunk_standalone.yaml
kubectl apply -f ./splunk_standalone.yaml -n $NAMESPACE_NAME
```

7. Wait till Splunk Standalone is created
```bash
until kubectl logs splunk-s1-standalone-0 -c splunk -n $NAMESPACE_NAME  | grep "Ansible playbook complete"; do sleep 1; done
```

8. Expose service of splunk standalone to access locally, all the ports will be mapped with freely available ports of local machine
```bash
kubectl port-forward svc/splunk-s1-standalone-service -n $NAMESPACE_NAME :8000 :8088 :8089 > ./exposed_splunk_ports.log 2>&1 &
```

9. Get the mapped ports of 8000, 8088, 8089 and update the pytest.ini accordingly.

10. Access the splunk ui and install the addon by "Install app from file",
 - `http://localhost:splunk-web-port/`
 - Install modinput helper addon downloaded in step-1 , as a prerequisite of execution of modinput tests.

11. If TEST_TYPE is `ui` then follow the below steps,
  - Download Browser's specific driver
     - For Chrome: download chromedriver
     - For Firefox: download geckodriver
     - For IE: download IEdriverserver
  - Put the downloaded driver into `test/ui/` directory, make sure that it is within the environment's PATH variable, and that it is executable
  - For Internet explorer, The steps mentioned at below link must be performed [selenium](https://github.com/SeleniumHQ/selenium/wiki/InternetExplorerDriver#required-configuration)

12. Execute Tests
##### Modinput_Functional
```bash
python -m pytest -vv --username=admin --password=Chang3d! --splunk-url=localhost --splunkd-port=<splunk-management-port> --remote -n 5 tests/modinput_functional
```
##### UI (local)
```bash
python -m pytest -vv --splunk-type=external --splunk-host=localhost --splunkweb-port=<splunk-web-port> --splunk-port=<splunk-management-port> --splunk-password=Chang3d! --browser=<browser> --splunk-hec-port=<splunk-hec-port> --local tests/ui 
```
##### UI (in Saucelabs)
  - Set the following env variables with appropriate values
```bash
export SAUCE_USERNAME=<username>
export SAUCE_PASSWORD=<password>
export SAUCE_TUNNEL_PARENT=<parent-tunnel-name>
export SAUCE_TUNNEL_ID=<tunnel-id>
export SAUCE_IDENTIFIER=$SAUCE_TUNNEL_ID
export JOB_NAME="k8s::<addon-name>-<browser>-<unique-string>"
```
>- Best practice is to keep the JOB_NAME unique for each test execution
- Set up sauce-connect proxy by following the steps mentioned [here](https://docs.saucelabs.com/secure-connections/sauce-connect/installation/) in another terminal by exporting above mentioned variables
- Add `domain_name` mapped to `127.0.0.1` or `localhost` in /etc/hosts

```
python -m pytest -vv --splunk-type=external --splunk-password=Chang3d! --splunk-host=<domain_name> --splunkweb-port=<splunk-web-port> --splunk-port=<splunk-management-port> --splunk-hec-port=<splunk-hec-port> --browser=<browser> tests/ui
```

### NOTE: Once test-execution is done user needs to manually turn off the sauce-connect proxy

13. Delete the ./exposed_splunk_ports.log file and other kubernetes resources

```bash
kubectl delete -f ./splunk_standalone.yaml -n $NAMESPACE_NAME
sleep 30
kubectl delete secret splunk-$NAMESPACE_NAME-secret -n $NAMESPACE_NAME
kubectl delete -f ./namespace.yaml -n $NAMESPACE_NAME
sleep 60
```

## With External
### Prerequisitory

- Git
- Python3 (>=3.7)
- Splunk along with addon installed and HEC token created
- If Addon support the syslog data ingestion(sc4s)
  - Docker
  - Docker-compose

### Steps

1. Clone the repository
```bash
git clone git@github.com:splunk/<repo name>.git
cd <repo dir>
```

2. Install Requirements
```bash
pip install poetry
poetry export --without-hashes --dev -o requirements_dev.txt
pip install -r requirements_dev.txt
```

3. Setup SC4S (for SC4S based addons)
- If addon requires sc4s, need to update following in `docker-compose.yml` used to spin sc4s, (`docker-compose.yml` is already present in addon repo)

- `docker-compose.yml` file contents
```yml
sc4s:
    image: splunk/scs:<<SC4S_VERSION>>
    hostname: sc4s
    #When this is enabled test_common will fail
    #    command: -det
    ports:
      - "514"
      - "601"
      - "514/udp"
      - "9000"
      - "5000-5050"
      - "5000-5050/udp"
      - "6514"
    stdin_open: true
    tty: true
    environment:
      - SPLUNK_HEC_URL=<<SPLUNK_HEC_URL>>
      - SPLUNK_HEC_TOKEN=<<SPLUNK_HEC_TOKEN>>
      - SC4S_SOURCE_TLS_ENABLE=no
      - SC4S_DEST_SPLUNK_HEC_TLS_VERIFY=no
      - SC4S_LISTEN_CISCO_ESA_TCP_PORT=9000
      - SC4S_LISTEN_JUNIPER_NETSCREEN_TCP_PORT=5000
      - SC4S_LISTEN_CISCO_ASA_TCP_PORT=5001
      - SC4S_LISTEN_CISCO_IOS_TCP_PORT=5002
      - SC4S_LISTEN_CISCO_MERAKI_TCP_PORT=5003
      - SC4S_LISTEN_JUNIPER_IDP_TCP_PORT=5004
      - SC4S_LISTEN_PALOALTO_PANOS_TCP_PORT=5005
      - SC4S_LISTEN_PFSENSE_TCP_PORT=5006
      - SC4S_LISTEN_CISCO_ASA_UDP_PORT=5001
      - SC4S_LISTEN_CISCO_IOS_UDP_PORT=5002
      - SC4S_LISTEN_CISCO_MERAKI_UDP_PORT=5003
      - SC4S_LISTEN_JUNIPER_IDP_UDP_PORT=5004
      - SC4S_LISTEN_PALOALTO_PANOS_UDP_PORT=5005
      - SC4S_LISTEN_PFSENSE_UDP_PORT=5006
      - SC4S_ARCHIVE_GLOBAL=no
      - SC4S_LISTEN_CHECKPOINT_SPLUNK_NOISE_CONTROL=yes
```
- SC4S_VERSION: used by sc4s to spin up.
- SPLUNK_HEC_TOKEN: HEC token generated by external splunk instance.
- SPLUNK_HEC_URL: HEC url of the external splunk instance.
- And execute following to spin sc4s in your local or any other machine.

```
docker-compose -f docker-compose.yml up -d sc4s
```

- Validate the sc4s is up and running via `docker ps` with the given version and connected to splunk instance by checking if sc4s startup events are available in splunk instance at `sourcetype = sc4s:events:startup:out`
- Update the sc4s-host and sc4s-port value in pytest.ini file.
port value mapped to 514/tcp can be obtained via `docker ps` command
- Create required SC4S indexes using the following SPL

```
wget $( curl -s https://api.github.com/repos/splunk/splunk-configurations-base-indexes/releases/latest \ | jq -r '.assets[] | select((.name | contains("spl")) and (.name | contains("search_head") | not) and (.name | contains("indexers") | not ) and (.name | contains("forwarders") | not)) | .browser_download_url ')
```

4. Run Tests
#### Knowledge

```bash
python -m pytest -vv --splunk-type=external --splunk-app=<path-to-addon-package> --splunk-data-generator=<path to pytest-splunk-addon-data.conf file> --splunk-host=<hostname> --splunk-port=<splunk-management-port> --splunk-user=<username> --splunk-password=<password> --splunk-hec-token=<splunk_hec_token> --sc4s-host=<sc4s_host> --sc4s-port=<sc4s_port>
```

#### UI
1. Set all variables in environment mentioned at [test_credentials.env](test_credentials.env) file with appropriate values encoded with base64.
2. Download Browser's specific driver
    - For Chrome: download chromedriver
    - For Firefox: download geckodriver
    - For IE: download IEdriverserver
3. Put the downloaded driver into `test/ui/` directory, make sure that it is within the environment's PATH variable, and that it is executable
4. For Internet explorer, The steps mentioned at below link must be performed [selenium](https://github.com/SeleniumHQ/selenium/wiki/InternetExplorerDriver#required-configuration)
5. Execute the test cases

- To execute the tests on saucelabs set the required env variable for saucelabs

```
export SAUCE_USERNAME=<username>
export SAUCE_PASSWORD=<password>
export JOB_NAME="Local::<addon-name>-browser-<unique-string>"
```
>- Best practice is to keep the JOB_NAME unique for each test execution
- Remove --local param from the below pytest command and tests will be executed on saucelabs
```bash
python -m pytest -vv --browser=<browser> --local --splunk-host=<web_url> --splunk-port=<mgmt_url> --splunk-user=<username> --splunk-password=<password>
```

#### Modinput
  - Install [splunk-add-on-for-modinput-test](https://github.com/splunk/splunk-add-on-for-modinput-test/releases/latest/) addon in splunk and set all variables in environment mentioned at [test_credentials.env](test_credentials.env) file with appropriate values encoded with base64 or add variables in pytest command mentioned in conftest file.
  - Update the pytest command with additional params if required for the addon.

```bash
python -m pytest -vv --username=<splunk_username> --password=<splunk_password> --splunk-url=<splunk_url> --remote
```