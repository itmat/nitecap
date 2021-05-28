export type Environment = {
  account?: string;
  region?: string;
  production: boolean;
  subdomainName: string;
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
