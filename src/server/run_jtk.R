#!/usr/bin/env Rscript
# This script meant to be used only by nitecap

library(MetaCycle);
library("readr");
library("stringr")

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_file <- args[2]
timepoints_per_cycle <- strtoi(args[3])
num_replicates <- as.integer(unlist(str_split(args[4], ",")))
num_cycles <- strtoi(args[5])

timepoints <-Reduce(c, sapply(1:length(num_replicates), function(i) {rep(i,num_replicates[i])}))

res <- meta2d(
    infile=input_file,
    outdir = output_file,
    timepoints = timepoints,
    filestyle = 'txt',
    minper = timepoints_per_cycle,
    maxper = timepoints_per_cycle,
    cycMethod = c("ARS", "JTK", "LS"),
    combinePvalue = "bonferroni",
    ARSdefaultPer = timepoints_per_cycle,
    outputFile = FALSE,
)
ARS <- res$ARS
JTK <- res$JTK
LS <- res$LS

pvals <- list(
    ARS_P = ARS$pvalue,
    ARS_Q = ARS$fdr_BH,
    JTK_P = JTK$ADJ.P,
    JTK_Q = JTK$BH.Q,
    LS_P = LS$p,
    LS_Q = LS$BH.Q
);
L <- max(unlist(lapply(pvals, length)));
fill_null <- function(col) { if (is.null(col)) { rep(NA, L) } else {col}};
pvals <- as.data.frame(lapply(pvals, fill_null));

write_tsv(pvals, path=output_file)
