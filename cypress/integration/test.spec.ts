import environment from "./.env";

describe("Standard visitors workflow", () => {
  it("loads a spreadsheets and displays the computation results", () => {
    cy.visit(environment.URL);
    cy.contains("Load new spreadsheet").click();
    cy.get("input[type='file']").attachFile("spreadsheet.tsv");
    cy.get("#submit_btn").click();
    cy.get("body").should("contain", "Collect Data");
    cy.contains("div", "Number of total timepoints")
      .find("input")
      .type("24")
      .blur();
    cy.contains("div", "Number of timepoints per cycle", { matchCase: false })
      .find("input")
      .type("6")
      .blur();
    cy.contains("Submit").click();
  });
});
