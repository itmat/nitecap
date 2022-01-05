import * as ecs from "aws-cdk-lib/aws-ecs";

export default function mountEbsVolume(
  deviceName: string,
  mountPoint: string,
  cluster: ecs.Cluster
) {
  cluster.autoscalingGroup?.addUserData(
    `mkdir ${mountPoint}`,
    `mount ${deviceName} ${mountPoint}`,
    `DEVICE_UUID=$(blkid | grep ${deviceName} | cut -d '"' -f 2)`,
    `echo UUID=$DEVICE_UUID  ${mountPoint}  xfs  defaults,nofail  0  2 >> /etc/fstab`
  );
}
