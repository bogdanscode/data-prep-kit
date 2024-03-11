#!/usr/bin/env bash

op=$1

source ${KIND_DIR}/hack/common.sh

deploy() {
	kubectl apply -f ${KIND_DIR}/hack/ray_api_server_ingress.yaml
	kubectl apply -f ${KIND_DIR}/hack/kfp_ingress.yaml
}

delete(){
	kubectl delete -f ${KIND_DIR}/hack/ray_api_server_ingress.yaml
	kubectl delete -f ${KIND_DIR}/hack/kfp_ingress.yaml
}

usage(){
        cat <<EOF
"Usage: ./ingress.sh [deploy|cleanup]"
EOF
}

case "$op" in
	cleanup)
		header_text "Uninstalling NGINX"
		delete
		;;
	deploy)
		header_text "Installing NGINX"
		deploy
		;;
	*)
		usage
		;;
esac
