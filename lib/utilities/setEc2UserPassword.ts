import * as ecs from "@aws-cdk/aws-ecs";
import * as secretsmanager from "@aws-cdk/aws-secretsmanager";

export default function setEc2UserPassword(
  cluster: ecs.Cluster,
  password: secretsmanager.Secret
) {
  if (!cluster.autoscalingGroup)
    throw Error("Autoscaling group does not exist")

  password.grantRead(cluster.autoscalingGroup);

  cluster.autoscalingGroup?.addUserData(
    `yum -y install jq unzip`,
    `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"`,
    `unzip awscliv2.zip`,
    `./aws/install`,
    `aws secretsmanager get-secret-value --secret-id ${password.secretFullArn} > password.json`,
    `echo "ec2-user:$(jq -r .SecretString password.json)" | chpasswd`,
    `rm password.json awscliv2.zip /usr/local/bin/aws /usr/local/bin/aws_completer`,
    `rm -rf ./aws /usr/local/aws-cli`,
    `yum -y remove jq unzip`,
    `yum clean all`
  );
}
