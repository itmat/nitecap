#!/usr/bin/env python
import json

# Basic script to process a pathways list file from Greg into a json-style file
genes = [line.strip().split() for line in open("/Users/tgbrooks/Downloads/pathways/curated_gene_sets.txt").readlines()]
as_dict = [{'name': gene[0], 'url': gene[1], 'ids': gene[2:]} for gene in genes]

output = open("static/js/pathway_list.js", "w")
output.write("let PATHWAYS = ");
json.dump(as_dict, output)
