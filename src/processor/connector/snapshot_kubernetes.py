import json
import ast
import hashlib
import time
import os
from datetime import datetime
from openapi_schema_to_json_schema import to_json_schema
from processor.helper.json.json_utils import get_field_value,json_from_file,save_json_to_file,\
    make_snapshots_dir,store_snapshot,get_field_value_with_default
from processor.logging.log_handler import getlogger
from processor.helper.config.config_utils import config_value, get_test_json_dir,framework_dir
from kubernetes import client,config
import kubernetes.client
from kubernetes.client.rest import ApiException
from processor.connector.snapshot_utils import validate_snapshot_nodes
from processor.database.database import COLLECTION




logger = getlogger()


def get_kubernetes_structure_path(snapshot_source):
    """
    get_kubernetes_structure_path will get kubernetes connector file path
    from configuration file.
    """
    connector_path = '%s/%s/%s.json' % \
                 (framework_dir(),config_value('KUBERNETES','kubernetsStructureFolder'),snapshot_source)
    return connector_path

def get_kubernetes_structure_data(snapshot_source):
    kubernetes_structure_path = get_kubernetes_structure_path(snapshot_source)
    return json_from_file(kubernetes_structure_path)



def get_kube_apiserver_info():
    container_path = get_test_json_dir()
    return container_path

def make_kubernetes_snapshot_template(node,node_path,snapshot,kubernetes_snapshot_data):
    node_db_record_data= node_db_record(node,node_path,snapshot)
    node_db_record_data['json']=kubernetes_snapshot_data

    return node_db_record_data



def create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
    api_instance = None
    service_account_secret = get_client_secret(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace)

    if service_account_secret == "" :
        logger.error("\t\t ERROR : can not find secret for service account : %s" % (snapshot_serviceAccount))
        # return api_instance
    cluster_url = get_field_value(kubernetes_structure_data,'clusterUrl')
    api_instance = create_kube_apiserver_instance_client(cluster_url,service_account_secret,node_type)
    return api_instance

def get_client_secret(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace):
    namespaces = get_field_value(kubernetes_structure_data,'namespaces')
    service_account_secret = ""
    for namespace in namespaces :
        service_accounts = get_field_value(namespace,'serviceAccounts')
        for service_account in service_accounts :
            if snapshot_serviceAccount == service_account['name'] and namespace['namespace'] in snapshot_namespace :
                service_account_secret = get_field_value(service_account['name'],'secret')
                if service_account_secret is None:
                    service_account_secret = os.getenv(snapshot_serviceAccount, None)
    return service_account_secret 

def create_kube_apiserver_instance_client(cluster_url,service_account_secret,node_type):
    configuration = kubernetes.client.Configuration()
    token = '%s' % (service_account_secret)
    configuration.api_key={"authorization":"Bearer "+ token}
    configuration.host = cluster_url
    configuration.verify_ssl=False 
    configuration.debug = False
    client.Configuration.set_default(configuration)
    if node_type in ["pod","service","serviceaccount"]:
        api_client = client.CoreV1Api()
    if node_type in ["deployment","replicaset"]:
        api_client = client.AppsV1Api()
    if node_type in ["networkpolicy"]:
        api_client = client.NetworkingV1Api()
    if node_type in ["podsecuritypolicy"]:
        api_client = client.PolicyV1beta1Api()
    if node_type in ["rolebinding"]:
        api_client = client.RbacAuthorizationV1beta1Api()
    return api_client

def get_kubernetes_snapshot_data(kubernetes_structure_data,path,node_type,snapshot_serviceAccount,snapshot_namespace):
    api_response = None
    object_name = path.split("/")[-1]
    api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
    try:
        if node_type == "pod":
            snapshot_namespace = path.split("/")[3]
            api_response = api_instance.read_namespaced_pod(name=object_name,namespace=snapshot_namespace)

        if node_type == "deployment":
            snapshot_namespace = path.split("/")[4]
            api_response = api_instance.read_namespaced_deployment(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information deployment : %s', object_name)

        if node_type == "replicaset":
            snapshot_namespace = path.split("/")[4]
            api_response = api_instance.read_namespaced_replica_set(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information replicaset : %s', object_name)

        if node_type == "service":
            snapshot_namespace = path.split("/")[3]
            api_response = api_instance.read_namespaced_service(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information replicaset : %s', object_name)

        if node_type == "networkpolicy":
            snapshot_namespace = path.split("/")[4]
            api_response = api_instance.read_namespaced_network_policy(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information networkPolicy : %s', object_name)

        if node_type == "podsecuritypolicy":
            api_response = api_instance.read_pod_security_policy(name=object_name)
            # logger.info('error in calling api for getting information  podSecurityPolicy: %s', object_name)

        if node_type == "rolebinding":
            snapshot_namespace = path.split("/")[4]
            api_response = api_instance.read_namespaced_role_binding(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information  roleBinding: %s', object_name)

        if node_type == "serviceaccount":
            snapshot_namespace = path.split("/")[3]
            api_response = api_instance.read_namespaced_service_account(name=object_name,namespace=snapshot_namespace)
            # logger.info('error in calling api for getting information  roleBinding: %s', object_name)
    except Exception as ex :
        logger.info('\t\tERROR : error in calling api for getting information %s : %s',node_type, object_name)
        logger.info('\t\tERROR : %s',ex)
        
    api_response_dict = todict(api_response)  
    return api_response_dict

def todict(obj):
    if hasattr(obj, 'attribute_map'):
        result = {}
        for k,v in getattr(obj, 'attribute_map').items():
            val = getattr(obj, k)
            if val is not None:
                result[v] = todict(val)
        return result
    elif type(obj) == list:
        return [todict(x) for x in obj]
    elif type(obj) == datetime:
        return str(obj)
    else:
        return obj

def node_db_record(node,node_path,snapshot):
    collection = node['collection'] if 'collection' in node else COLLECTION
    data = {
    "structure":"kubernetes",
    "reference": snapshot['namespace'],
    "source": snapshot['source'],
    "path":node_path,
    "timestamp": int(time.time() * 1000),
    "queryuser": snapshot['serviceAccount'],
    "checksum":hashlib.md5("{}".encode('utf-8')).hexdigest(),
    "node": node,
    "snapshotId":node['snapshotId'],
    "collection": collection.replace('.', '').lower(),
    "json": {}
    }
    return data

def get_lits(node_type,namespace,kubernetes_structure_data,snapshot_serviceAccount):

    master_snapshot_func = {
        'pod' : get_list_namespaced_pods,
        'networkpolicy' : get_list_namespaced_network_policy,
        'podsecuritypolicy' : get_list_namespaced_pod_security_policy,
        'rolebinding' : get_list_namespaced_role_binding,
        'serviceaccount' : get_list_namespaced_service_account
    }
    list_item=[]
    try:
         list_item.append(master_snapshot_func[node_type](
                namespace,
                kubernetes_structure_data,
                snapshot_serviceAccount,
                namespace,
                node_type))

    except Exception as ex :
        logger.info('\t\tERROR : error in calling api for getting information %s ',node_type)
        logger.info('\t\tERROR : %s',ex)
    
    return list_item

def get_list_namespaced_pods(namespace,kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
        pod_items = []
        api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
        api_response = api_instance.list_namespaced_pod(namespace=namespace)
        api_response_dict = todict(api_response) 
        api_response_dict_items = get_field_value(api_response_dict,'items')
        for api_response_dict_item in api_response_dict_items :
            pod_name = get_field_value(api_response_dict_item,'metadata.name')
            pod_path = "api/v1/namespaces/%s/pods/%s" % (namespace,pod_name)
            pod_items.append({
                'namespace': namespace,
                'paths':[
                    pod_path
                ]
            })
        return pod_items

def get_list_namespaced_network_policy(namespace,kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
    network_policy_items = []
    api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
    api_response = api_instance.list_namespaced_network_policy(namespace=namespace)
    api_response_dict = todict(api_response) 
    api_response_dict_items = get_field_value(api_response_dict,'items')
    for api_response_dict_item in api_response_dict_items :
        network_policy_name = get_field_value(api_response_dict_item,'metadata.name')
        network_policy_path = "apis/networking.k8s.io/v1/namespaces/%s/networkpolicies/%s" % (namespace,network_policy_name)
        network_policy_items.append({
            'namespace': namespace,
            'paths':[
                network_policy_path
            ]
        })
    return network_policy_items

def get_list_namespaced_pod_security_policy(namespace,kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
    pod_security_policy_items = []
    api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
    api_response = api_instance.list_pod_security_policy()
    api_response_dict = todict(api_response) 
    api_response_dict_items = get_field_value(api_response_dict,'items')
    for api_response_dict_item in api_response_dict_items :
        pod_security_policy_name = get_field_value(api_response_dict_item,'metadata.name')
        pod_security_policy_path = "apis/policy/v1beta1/podsecuritypolicies/%s" % (pod_security_policy_name)
        pod_security_policy_items.append({
            'namespace': namespace,
            'paths':[
                pod_security_policy_path
            ]
        })
    return pod_security_policy_items

def get_list_namespaced_role_binding(namespace,kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
    role_binding_items = []
    api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
    api_response = api_instance.list_namespaced_role_binding(namespace=namespace)
    api_response_dict = todict(api_response) 
    api_response_dict_items = get_field_value(api_response_dict,'items')
    for api_response_dict_item in api_response_dict_items :
        role_binding_name = get_field_value(api_response_dict_item,'metadata.name')
        role_binding_path = "apis/rbac.authorization.k8s.io/v1beta1/namespaces/%s/rolebindings/%s" % (namespace,role_binding_name)
        role_binding_items.append({
            'namespace': namespace,
            'paths':[
                role_binding_path
            ]
        })
    return role_binding_items

def get_list_namespaced_service_account(namespace,kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type):
    service_account_items = []
    api_instance = create_kube_apiserver_instance(kubernetes_structure_data,snapshot_serviceAccount,snapshot_namespace,node_type)
    api_response = api_instance.list_namespaced_service_account(namespace=namespace)
    api_response_dict = todict(api_response) 
    api_response_dict_items = get_field_value(api_response_dict,'items')
    for api_response_dict_item in api_response_dict_items :
        service_account_name = get_field_value(api_response_dict_item,'metadata.name')
        service_account_path = "api/v1/namespaces/%s/serviceaccounts/%s" % (namespace,service_account_name)
        service_account_items.append({
            'namespace': namespace,
            'paths':[
                service_account_path
            ]
        })
    return service_account_items

def generate_crawler_snapshot(snapshot,container,node,node_type,node_path,snapshot_data,kubernetes_structure_data,snapshot_serviceAccount):
    snapshot_source = get_field_value(snapshot, 'source')
    snapshot_serviceAccount =  get_field_value(snapshot,'serviceAccount')
    snapshot_namespaces = get_field_value(snapshot,'namespace')
    snapshot_nodes = get_field_value(snapshot,'nodes')
    snapshot_masterSnapshotId = get_field_value(node,'masterSnapshotId')
    collection = node['collection'] if 'collection' in node else COLLECTION
    parts = snapshot_source.split('.')
    namespace = get_field_value_with_default(snapshot,'namespace',"")
    node_type = get_field_value_with_default(node, 'type',"")
    resource_items = []
    for snapshot_namespace in snapshot_namespaces:
        resource_items+=get_lits(
            node_type=node_type,
            namespace=snapshot_namespace,
            kubernetes_structure_data=kubernetes_structure_data,
            snapshot_serviceAccount=snapshot_serviceAccount)

    snapshot_data[node['masterSnapshotId']] = []
    found_old_record = False
    for resource_item in resource_items :
        for masterSnapshotId,snapshot_list in snapshot_data.items() :
            old_record = None
            if isinstance(snapshot_list, list):
                for item in snapshot_list:
                    if item["paths"] == node_path:
                        old_record = item
                if old_record:
                    found_old_record = True
                    if node['masterSnapshotId'] not in old_record['masterSnapshotId']:
                        old_record['masterSnapshotId'].append(
                            node['masterSnapshotId'])        
        for index,resource_namespaced_item in enumerate(resource_item):

            snapshot_data[node['masterSnapshotId']].append({
                            "masterSnapshotId" : [node['masterSnapshotId']],
                            "snapshotId": '%s%s_%s' % (node['masterSnapshotId'],resource_namespaced_item['namespace'], str(index)),
                            "type": node_type,
                            "collection": node['collection'],
                            "paths": resource_namespaced_item['paths'],
                            "status" : "active",
                            "validate" : node['validate'] if 'validate' in node else True
                        })
    return snapshot_data



def populate_kubernetes_snapshot(snapshot, container=None):
    snapshot_source = get_field_value(snapshot, 'source')
    snapshot_serviceAccount = get_field_value(snapshot,'serviceAccount')
    snapshot_namespace = get_field_value(snapshot,'namespace')
    snapshot_nodes = get_field_value(snapshot,'nodes')
    snapshot_data, valid_snapshotids = validate_snapshot_nodes(snapshot_nodes)
    kubernetes_structure_data = get_kubernetes_structure_data(snapshot_source)

    if valid_snapshotids  and snapshot_nodes:
        logger.debug(valid_snapshotids)
        try :
            for node in snapshot_nodes:
                validate = node['validate'] if 'validate' in node else True
                logger.info(node)
                node_paths = get_field_value(node,'paths')
                node_type = get_field_value(node,'type')
                for node_path in node_paths:
                    if 'snapshotId' in node:
                        if validate:
                            kubernetes_snapshot_data = get_kubernetes_snapshot_data(
                            kubernetes_structure_data,
                            node_path,node_type,
                            snapshot_serviceAccount,
                            snapshot_namespace) 
                            if kubernetes_snapshot_data :
                                error_str = kubernetes_snapshot_data.pop('error', None)
                                kubernetes_snapshot_template = make_kubernetes_snapshot_template(
                                    node,
                                    node_path,
                                    snapshot,
                                    kubernetes_snapshot_data
                                )
                                snapshot_dir = make_snapshots_dir(container)
                                if snapshot_dir:
                                    store_snapshot(snapshot_dir, kubernetes_snapshot_template)                                

                                if "masterSnapshotId" in node :
                                    snapshot_data[node['snapshotId']] = node['masterSnapshotId']
                                elif "snapshotId" in node :
                                    snapshot_data[node['snapshotId']] = False if error_str else True
                            else:
                                node['status'] = 'inactive'
                    elif 'masterSnapshotId' in node:
                        snapshot_data = generate_crawler_snapshot(
                            snapshot,
                            container,
                            node,
                            node_type,
                            node_path,
                            snapshot_data,
                            kubernetes_structure_data,
                            snapshot_serviceAccount)
                    


        except Exception as ex:
                logger.info('can not connect to kubernetes cluster: %s', ex)
                raise ex
    return snapshot_data