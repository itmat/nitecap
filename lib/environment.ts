type LoggingLevel =
  | "CRITICAL"
  | "ERROR"
  | "WARNING"
  | "INFO"
  | "DEBUG"
  | "NOTSET";

export type Environment = {
  name: string;
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
      LOG_LEVEL: LoggingLevel;
      LOGS_DIRECTORY_PATH: string;
      DATABASE_FOLDER: string;
      DATABASE_FILE: string;
      UPLOAD_FOLDER: string;
      RECAPTCHA_SITE_KEY: string;
      RECAPTCHA_SECRET_KEY: string;
      [key: string]: string;
    };
  };
};
