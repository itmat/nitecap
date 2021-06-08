import environment from "./.env";

const addWhitespace = (result) =>
  `\n                                                        ${result}\n                                                    `;

describe("Standard visitors workflow", () => {
  it("loads a spreadsheet and computes ARSER p-value", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Load new spreadsheet").click();
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
    cy.get("body").should("contain", "Loading...");
    cy.get("body").should("contain", "Spreadsheet Rows");
    cy.contains("tr>td", "ARS")
      .next()
      .contains("Unknown")
      .contains("PENDING")
      .contains("100%", { timeout: 20000 });
    cy.contains("tr>td", "ARS")
      .next()
      .should("have.text", addWhitespace("p: 4.4e-10"));
  });

  it("loads a spreadsheet, displays the computation results, and generates a heat map", () => {
    cy.visit(environment.baseUrl);
    cy.contains("Load new spreadsheet").click();
    cy.get("input[type='file']").attachFile("raw.8.9.2.txt");
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

    for (let [algorithm, result] of [
      ["Nitecap", "p: 0.025"],
      ["JTK", "p: 0.058"],
      ["LS", "p: 0.115"],
      ["Cosinor", "p: 0.002"],
      ["ANOVA", "p: 0.252"],
      ["Amplitude", "5.927"],
      ["Peak-time", "4.667"],
      ["ARS", "p: N/A"],
    ])
      cy.contains("tr>td", algorithm)
        .next()
        .should("have.text", addWhitespace(result));

    cy.contains("span", "Number of selected rows").find("input").type("0");
    cy.contains("a", "Heatmap").click();
    cy.contains("button", "Generate Heatmap").click();
    cy.get("[class^='heatmaplayer']")
      .find("image")
      .invoke("attr", "href")
      .should("eq", environment.pcaPlotBase64Image);
  });
});
