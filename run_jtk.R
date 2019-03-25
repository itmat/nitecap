#!/usr/bin/env Rscript
# This script meant to be used only by nitecap

library("readr")
library("stringr")
source("/var/www/flask_apps/nitecap/JTK_CYCLEv3.1.R")

args <- commandArgs(trailingOnly = TRUE)
input_file <- args[1]
output_file <- args[2]
timepoints_per_cycle <- strtoi(args[3])
num_replicates <- as.integer(unlist(str_split(args[4], ",")))
num_cycles <- strtoi(args[5])
hours_between_timepoints <- strtoi(args[6])

num_timepoints  = timepoints_per_cycle * num_cycles

datatable = read_tsv(input_file, col_names = TRUE)

jtkdist(num_timepoints, num_replicates)
periods <- c(timepoints_per_cycle) # only check for the base period (i.e. 24 hours)
jtk.init(periods, hours_between_timepoints)

res <- apply(datatable,1,function(z) {
  jtkx(z)
  c(JTK.ADJP,JTK.PERIOD,JTK.LAG,JTK.AMP)
})
res <- as.data.frame(t(res))
bhq <- p.adjust(unlist(res[,1]),"BH")
res <- cbind(bhq,res)
colnames(res) <- c("JTK_Q","JTK_P","PERIOD","LAG","AMPLITUDE")

write_tsv(res, path=output_file)
