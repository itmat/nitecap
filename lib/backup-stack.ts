import * as backup from "@aws-cdk/aws-backup";
import * as cdk from "@aws-cdk/core";

import * as environment from "./.env.json";

export class BackupStack extends cdk.Stack {
  readonly backupPlan: backup.BackupPlan;

  constructor(scope: cdk.Construct, id: string, props: cdk.StackProps) {
    super(scope, id, props);

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
