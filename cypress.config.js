const { defineConfig } = require("cypress");

const yaml = require("js-yaml");
const fs = require("fs");

const testing = yaml.load(
  fs.readFileSync(`nitecap/configuration/${process.env.configuration}.yaml`)
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
