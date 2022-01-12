#!/bin/sh
kubectl delete -f ./k8s_manifests/uf/uf_deployment_updated.yaml -n $namespace_name
sleep 30
kubectl delete -f ./k8s_manifests/uf/uf_service.yaml -n $namespace_name