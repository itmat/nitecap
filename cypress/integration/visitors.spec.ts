import environment from "./.env";

describe("Standard visitors workflow", () => {
  it("loads a spreadsheets and displays the computation results", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Load new spreadsheet").click();
    cy.get("input[type='file']").attachFile("spreadsheet.tsv");
    cy.contains("Submit").click();
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
    cy.get("body").should("contain", "Loading...");
    cy.get("body").should("contain", "Spreadsheet Rows");
    cy.contains("tr>td", "LS")
      .next()
      .contains("Unknown")
      .contains("PENDING")
      .contains("100%", { timeout: 10000 });
    cy.contains("tr>td", "LS")
      .next()
      .should(
        "have.text",
        "\n                                                        p: 9.5e-4\n                                                    "
      );
  });
});
