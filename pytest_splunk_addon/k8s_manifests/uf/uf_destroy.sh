#!/bin/sh
kubectl delete -f "$(dirname -- "$0")"/uf_deployment_updated.yaml -n $NAMESPACE_NAME
sleep 15
kubectl delete -f "$(dirname -- "$0")"/uf_service.yaml -n $NAMESPACE_NAME