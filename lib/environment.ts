export type Environment = {
  account?: string;
  region?: string;
  production: boolean;
  subdomainName: string;
  allowedCidrBlocks: string[];
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
