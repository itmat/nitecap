import * as backup from "@aws-cdk/aws-backup";
import * as cdk from "@aws-cdk/core";

import { Environment } from "./environment";

type BackupStackProps = cdk.StackProps & { environment: Environment };

export class BackupStack extends cdk.Stack {
  readonly backupPlan: backup.BackupPlan;

  constructor(scope: cdk.Construct, id: string, props: BackupStackProps) {
    super(scope, id, props);

    const environment = props.environment;

    let backupVault = new backup.BackupVault(this, "BackupVault", {
      removalPolicy: environment.production
        ? cdk.RemovalPolicy.RETAIN
        : cdk.RemovalPolicy.DESTROY,
    });

    this.backupPlan = backup.BackupPlan.dailyWeeklyMonthly5YearRetention(
      this,
      `${this.stackName}-BackupPlan`,
      backupVault
    );
  }
}
