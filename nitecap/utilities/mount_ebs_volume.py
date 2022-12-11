import aws_cdk.aws_ecs as ecs


def mount_ebs_volume(cluster: ecs.Cluster, device_name: str, mount_point: str):
    cluster.autoscaling_group.add_user_data(
        f"""mkdir {mount_point}""",
        f"""mount {device_name} {mount_point}""",
        f"""DEVICE_UUID=$(blkid | grep {device_name} | cut -d '"' -f 2)""",
        f"""echo UUID=$DEVICE_UUID  {mount_point}  xfs  defaults,nofail  0  2 >> /etc/fstab""",
    )
