let { defineConfig } = require("cypress");

let yaml = require("js-yaml");
let fs = require("fs");

let outputs = require("./cdk.outputs.json");
let configuration;

for (stack in outputs)
  if (stack.endsWith("ServerStack"))
    configuration = outputs[stack]["Configuration"];

let testing = yaml.load(
  fs.readFileSync(`nitecap/configuration/${configuration}.yaml`)
).testing;

module.exports = defineConfig({
  e2e: {
    baseUrl: testing.url,
    testUsers: testing.users,
    setupNodeEvents(on, config) {
      // implement node event listeners here
    },
  },
});
