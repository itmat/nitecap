import environment from "../.env";

describe("Standard users workflow", () => {
  it("signs the user in", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Login").click();
    cy.get("#username").type(environment.username);
    cy.get("#password").type(environment.password);
    cy.contains("button", "Login").click();
    cy.get("body").contains("Saved Spreadsheets")
  });
});
