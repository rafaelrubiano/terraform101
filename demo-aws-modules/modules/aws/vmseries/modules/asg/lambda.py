import boto3, botocore, os
from datetime import datetime

ec2_client = boto3.client('ec2')
asg_client = boto3.client('autoscaling')

def lambda_handler(event, context):
    if event["detail-type"] == "EC2 Instance-launch Lifecycle Action":
        instance_id = event["detail"]["EC2InstanceId"]
        subnet_id = get_subnet_id(instance_id)
        interface_id = create_interface(subnet_id, event, instance_id)
        log("debug: interface_id: {}".format(interface_id))

        attachment = attach_interface(interface_id, instance_id)
        log("debug: attachment: {}".format(attachment))
        delete = ec2_client.modify_network_interface_attribute(
            Attachment={
                'AttachmentId': attachment,
                'DeleteOnTermination': True,
            },
            NetworkInterfaceId= interface_id,
        )
        log("debug: delete on Termination: {}".format(delete))

        if interface_id and not attachment:
            log("Removing network interface {} after attachment failed.".format(interface_id))
            delete_interface(interface_id)

        try:
            asg_client.complete_lifecycle_action(
                LifecycleHookName=event['detail']['LifecycleHookName'],
                AutoScalingGroupName=event['detail']['AutoScalingGroupName'],
                LifecycleActionToken=event['detail']['LifecycleActionToken'],
                LifecycleActionResult='CONTINUE'
            )

            if attachment:
                log('MGT Interface and attachment for {} was created successfully'.format(instance_id))
            else:
                log('There was an error creating the MGT Interface and attachment for {}'.format(instance_id))

        except botocore.exceptions.ClientError as e:
            log("Error completing life cycle hook for instance {}: {}".format(instance_id, e.response['Error']['Code']))
            log('{"Error": "1"}')


def get_subnet_id(instance_id):
    try:
        result = ec2_client.describe_instances(InstanceIds=[instance_id])
        vpc_subnet_id = result['Reservations'][0]['Instances'][0]['SubnetId']
        instancezone = result['Reservations'][0]['Instances'][0]['Placement']['AvailabilityZone']
        current_subnet = ec2_client.describe_subnets(Filters=[{'Name': 'subnet-id','Values': [vpc_subnet_id]}])
        mgmt_subnet = current_subnet['Subnets'][0]['Tags'][0]['Value'].replace("data","mng")
        mgmt_subnet_id = ec2_client.describe_subnets(Filters=[{'Name':'tag:Name','Values':[mgmt_subnet]}])['Subnets'][0]['SubnetId']
        log("Subnet id: {}".format(mgmt_subnet_id))

    except botocore.exceptions.ClientError as e:
        log("Error describing the instance {}: {}".format(instance_id, e.response['Error']['Code']))
        vpc_subnet_id = None
        mgmt_subnet_id = None

    return mgmt_subnet_id

def create_interface(subnet_id, event,instance_id):
    network_interface_id = None
    if subnet_id:
        try:
            network_interface = ec2_client.create_network_interface(SubnetId=subnet_id, Groups=[os.environ['security_group_ids']])
            network_interface_id = network_interface['NetworkInterface']['NetworkInterfaceId']
            log("Created network interface for mgmt: {}".format(network_interface_id))
        except botocore.exceptions.ClientError as e:
            log("Error creating network interface: {}".format(e.response['Error']['Code']))

    return network_interface_id

def attach_interface(network_interface_id, instance_id):
    attachment = None

    if network_interface_id and instance_id:
        log("d1: network_interface_id: {}".format(network_interface_id))
        log("d1: instance_id: {}".format(instance_id))
        try:
            attach_interface = ec2_client.attach_network_interface(
                NetworkInterfaceId=network_interface_id,
                InstanceId=instance_id,
                DeviceIndex=1
            )
            attachment = attach_interface['AttachmentId']
            log("Created network attachment: {}".format(attachment))
        except botocore.exceptions.ClientError as e:
            log("Error attaching network interface: {}".format(e.response['Error']['Code']))

    return attachment


def delete_interface(network_interface_id):
    try:
        ec2_client.delete_network_interface(
            NetworkInterfaceId=network_interface_id
        )
        return True

    except botocore.exceptions.ClientError as e:
        log("Error deleting interface {}: {}".format(network_interface_id, e.response['Error']['Code']))


def log(message):
    print('{}Z {}'.format(datetime.utcnow().isoformat(), message))
