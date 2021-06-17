import environment from "./.env";

describe("Share links", () => {
  it("can create and view shares", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Login").click();
    cy.get("#username").type(environment.username);
    cy.get("#password").type(environment.password);
    cy.contains("button", "Login").click();
    cy.get("body").contains("Saved Spreadsheets");
    cy.get("body").contains("Load Data").click();
    cy.get("input[type='file']").attachFile("results.6.24.1.txt");
    cy.contains("Submit").click();
    cy.get("body").should("contain", "Collect Data");
    cy.contains("div", "Number of total timepoints")
      .find("input")
      .type("24")
      .blur();
    cy.contains("div", "Number of timepoints per cycle")
      .find("input")
      .type("6")
      .blur();
    cy.contains("Submit").click();
    cy.get("body").should("contain", "Spreadsheet Rows");
    cy.get("#share_spreadsheet").click();
    cy.get("#share_url").should("contain.text", "https://");
    cy.get("#share_url")
      .invoke("text")
      .then((link) => {
        cy.contains("button", "Close").click();
        cy.contains("Logout").click();
        cy.visit(link);
      });
    cy.get("body").should("contain", "results.6.24.1.txt");
    cy.contains("tr>td", "LS")
    .next()
    .should("contain.text", "p: 9.5e-4");
  });
});
