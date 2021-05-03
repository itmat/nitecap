import { expect as expectCDK, matchTemplate, MatchStyle } from '@aws-cdk/assert';
import * as cdk from '@aws-cdk/core';
import * as Nitecap from '../lib/nitecap-stack';

test('Empty Stack', () => {
    const app = new cdk.App();
    // WHEN
    const stack = new Nitecap.NitecapStack(app, 'MyTestStack');
    // THEN
    expectCDK(stack).to(matchTemplate({
      "Resources": {}
    }, MatchStyle.EXACT))
});
