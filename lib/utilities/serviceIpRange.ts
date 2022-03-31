import * as ec2 from "aws-cdk-lib/aws-ec2";

import * as fs from "fs";
import * as path from "path";

interface IpRanges {
  syncToken: string;
  createDate: string;
  prefixes: {
    ip_prefix: string;
    region: string;
    service: string;
    network_border_group: string;
  }[];
  ipv6_prefixes: {
    ipv6_prefix: string;
    region: string;
    service: string;
    network_border_group: string;
  }[];
}

const data = JSON.parse(
  fs.readFileSync(path.resolve(__dirname, "./ip-ranges.json")).toString()
) as IpRanges;

export default function serviceIpRange(service: string, region: string) {
  return data.prefixes
    .filter((entry) => entry.service === service)
    .filter((entry) => entry.region === region)
    .map((entry) => entry.ip_prefix)[0];
}
