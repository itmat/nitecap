export type Environment = {
  domainName: string;
  hostedZoneAttributes: {
    zoneName: string;
    hostedZoneId: string;
  };
  production: boolean;
  allowedCidrBlocks: string[];
  email: {
    verifiedRecipients: string[];
    serverAlarmsRecipients: string[];
    computationBackendAlarmsRecipients: string[];
    softBouncesRecipients: string[];
    complaintsRecipients: string[];
  };
  server: {
    storage: {
      deviceName: string;
      deviceMountPoint: string;
      snapshotId: string;
      containerMountPoint: string;
    };
    variables: {
      [key: string]: string;
    };
  };
};
