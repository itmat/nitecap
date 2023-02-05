describe("Standard visitors workflow", () => {
  it("loads a spreadsheet and computes ARSER p-value", () => {
    cy.visit("/");
    cy.contains("Load your data").click();
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
      .should("contain.text", "p: 4.4e-10");
  });

  it("loads a spreadsheet, displays the computation results, and generates a heat map", () => {
    cy.visit("/");
    cy.contains("Load your data").click();
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
      ["JTK", "p: 1.1e-8"],
      ["LS", "p: 0.008"],
      ["Cosinor", "p: 2.0e-8"],
      ["ANOVA", "p: 5.4e-6"],
      ["RAIN", "p: 1.7e-8"],
      ["JTK amplitude", "3.456"],
      ["JTK lag", "3.000"],
      ["JTK period", "24.000"],
      ["ARS", "p: N/A"],
    ])
      cy.contains("tr>td", algorithm)
        .next()
        .should("contain.text", result);

    cy.contains("span", "Number of selected rows").find("input").type("0");
    cy.contains("a", "Heatmap").click();
    cy.contains("button", "Generate Heatmap").click();

    cy.fixture("heatmap.png").then((heatmap) => {
      cy.get("[class^='heatmaplayer']")
        .find("image")
        .invoke("attr", "href")
        .should("eq", "data:image/png;base64," + heatmap);
    });
  });
});
