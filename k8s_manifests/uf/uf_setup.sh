#!/bin/sh
kubectl apply -f ./k8s_manifests/uf/uf_deployment_updated.yaml -n $namespace_name
kubectl wait deployment -n $namespace_name --for=condition=available --timeout=900s -l='app=uf'
# while [[ $(kubectl get pod -n $namespace_name -l='app=sc4s' -o 'jsonpath={..status.conditions[?(@.type=="Ready")].status}') != "True" ]]; do echo "waiting for sc4s pod" && sleep 1; done
kubectl wait pod -n $namespace_name --for=condition=ready --timeout=900s -l='app=uf'
kubectl apply -f ./k8s_manifests/uf/uf_service.yaml -n $namespace_name
sleep 30
kubectl port-forward svc/uf-service -n $namespace_name :8089 > ./exposed_uf_ports.log 2>&1 &
sleep 30
echo "UF up"