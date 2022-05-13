export type Environment = {
  name: string,
  account?: string;
  region?: string;
  production: boolean;
  subdomainName: string;
  allowedCidrBlocks: string[];
  server: {
    storage: {
      deviceName: string;
      deviceMountPoint: string;
      snapshotId?: string;
      containerMountPoint: string;
    };
    variables: {
      LOGS_DIRECTORY_PATH: string;
      [key: string]: string;
    };
  };
};
