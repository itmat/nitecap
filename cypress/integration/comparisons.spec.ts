import environment from "./.env";

describe("Comparisons", () => {
  it("compares two conditions", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Load new spreadsheet").click();
    cy.get("input[type='file']").attachFile("comparison/case.8.9.4.txt");
    cy.contains("Submit").click();
    cy.get("body").should("contain", "Collect Data");
    cy.contains("div", "Number of total timepoints")
      .find("input")
      .type("9")
      .blur();
    cy.contains("div", "Number of timepoints per cycle")
      .find("input")
      .type("8")
      .blur();
    cy.contains("Submit").click();
    cy.get("body").should("contain", "Loading...");
    cy.get("body").should("contain", "Spreadsheet Rows");
    cy.contains("Load Data").click();
    cy.get("body").should("contain", "Load Spreadsheet File");
    cy.get("input[type='file']").attachFile("comparison/control.8.9.4.txt");
    cy.contains("Submit").click();
    cy.get("body").should("contain", "Collect Data");
    cy.contains("div", "Number of total timepoints")
      .find("input")
      .type("9")
      .blur();
    cy.contains("div", "Number of timepoints per cycle")
      .find("input")
      .type("8")
      .blur();
    cy.contains("Submit").click();
    cy.contains("button", "Compare").click();
    cy.contains("a", "case.8.9.4.txt").click();
    cy.get("body").should("contain", "Spreadsheet Rows");

    // Wait until computation is complete
    cy.contains("tr>td", "Two-way ANOVA").next().as("Result");
    cy.get("@Result", { timeout: 15000 }).should("contain.text", "p: 1.000");

    cy.contains("span", "Number of selected rows")
      .find("input")
      .type("{backspace}8{enter}")
      .blur();

    for (let [algorithm, result] of [
      ["Two-way ANOVA", "p: 2.2e-4"],
      ["Main Effect Diff", "p: 0.836"],
      ["Phase Difference", "p: 0.929"],
      ["Amplitude Difference", "p: 1.1e-7"],
      ["Damping", "p: 0.005"],
    ]) {
      cy.contains("tr>td", algorithm).next().should("contain.text", result);
    }
  });
});
