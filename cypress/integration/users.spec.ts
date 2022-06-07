import environment from "../.env";

let user = environment.users[0]

describe("Standard users workflow", () => {
  it("signs the user in", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Login").click();
    cy.get("#username").type(user.name);
    cy.get("#password").type(user.password);
    cy.contains("button", "Login").click();
    cy.get("body").contains("Saved Spreadsheets")
  });
});
