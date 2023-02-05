let [user] = Cypress.config("testUsers")

describe("Standard users workflow", () => {
  it("signs the user in", () => {
    cy.visit("/");
    cy.contains("Login").click();
    cy.get("#username").type(user.name);
    cy.get("#password").type(user.password);
    cy.contains("button", "Login").click();
    cy.get("body").contains("Saved Spreadsheets")
  });
});
