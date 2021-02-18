library(biomaRt);
library(dplyr);
library(jsonlite);

# TODO: update this when you run this file
work.dir <- "C:/Users/tgb/nitecap/"

species.list <- c("mmusculus", "hsapiens", "dmelanogaster");
kegg.species.list <- c("mmu", "hsa", "dme");
#TODO: to include any different ID types, we would have to update the group_by function
id_types <- c("ensembl_gene_id");
ensembl_mart <- useMart("ensembl");

# Use this to check the avialable datasets (to find species)
#datasets <- listDatasets(mart);

# Load the child-parent GO ontology relationships
# Table of child->parent relationships mapping GO id's to each other
go_parents <- read.table(paste(work.dir, "pathway_analysis/processed_obo.txt", sep=''), sep="\t", header=TRUE);

# GO term definitions
# Generate from running process_obo_file.py
go_definitions <- read.table(paste(work.dir, "pathway_analysis/go_definitions.txt", sep=''), sep="\t", header=TRUE, quote="");

human_pathways <- getBM(attributes=c("ensembl_gene_id", "go_id"), mart=useDataset("hsapiens_gene_ensembl", ensembl_mart);

# Gather the GO terms from ENSEMBL
for (species in species.list) {
    mart <- useDataset(paste(species, "_gene_ensembl", sep=''), ensembl_mart);
    for (id_type in id_types) {
        bm <- getBM(attributes=c(id_type, "go_id"), mart=mart);
        bm <- bm %>%
            filter(go_id != "")

        # If a gene is annotated to a GO term, also annotate it to parent terms
        with_parents <- bm %>%
            left_join(go_parents, by=c("go_id" = "child")) %>%
            select(id_type, "parent") %>%
            rename(go_id = parent) %>%
            distinct()
        all_annotations <- bind_rows(bm, with_parents) %>% distinct()


        # Output as json, grouping by the GO terms
        objectified <- all_annotations %>%
            group_by(go_id) %>%
            summarise(feature_ids = list(ensembl_gene_id),) %>%
            left_join(go_definitions, by="go_id") %>%
            replace_na(list(name = "unkown pathway")) %>%
            rename(pathway = go_id);
        objectified$url = paste("https://www.ebi.ac.uk/QuickGO/term/", objectified$pathway, sep='');

        write_json(objectified, paste(work.dir, "static/json/", species, ".", id_type, ".GO.pathways.json", sep=''));

        # If not human, we get homologous genes and form pathways from those
        if (species != "hsapiens") {
            homologs <- getBM(attributes=c(id_type, "hsapiens_homolog_ensembl_gene"), mart=mart);
            homolog_pathways <- human_pathways %>%
                inner_join(homologs, by=c("ensembl_gene_id" = "hsapiens_homolog_ensembl_gene")) %>%
                filter(go_id != "") %>%
                select(ensembl_gene_id.y, go_id) %>%
                rename(ensembl_gene_id = ensembl_gene_id.y);

            # If a gene is annotated to a GO term, also annotate it to parent terms
            with_parents <- homolog_pathways %>%
                left_join(go_parents, by=c("go_id" = "child")) %>%
                select(id_type, "parent") %>%
                rename(go_id = parent) %>%
                distinct()
            all_annotations <- bind_rows(homolog_pathways, with_parents) %>% distinct()


            # Output as json, grouping by the GO terms
            objectified <- all_annotations %>%
                group_by(go_id) %>%
                summarise(feature_ids = list(ensembl_gene_id),) %>%
                left_join(go_definitions, by="go_id") %>%
                replace_na(list(name = "unkown pathway")) %>%
                rename(pathway = go_id);
            objectified$url = paste("https://www.ebi.ac.uk/QuickGO/term/", objectified$pathway, sep='');

            write_json(objectified, paste(work.dir, "static/json/", species, ".", id_type, ".GO.homology_pathways.json", sep=''));
        }
    }
}

# Gather the KEGG terms
library(KEGGREST);

for (i in seq_len(length(kegg.species.list))) {
    species = species.list[i];
    kegg.species = kegg.species.list[i];

    kegg_pathways <-  keggLink(kegg.species, "pathway");
    kegg_pathways <- data.frame(list("kegg_geneid"=unname(kegg_pathways), "pathway"=names(kegg_pathways)));
    kegg_pathway_info <- keggList("pathway", kegg.species);
    kegg_pathway_info <- data.frame(list("pathway"=names(kegg_pathway_info), "name"=unname(kegg_pathway_info)));
    kegg_pathway_info$name = sub(" *-[^-]*", "",kegg_pathway_info$name); # remove the species name
    kegg_pathway_info$url = paste( "https://www.genome.jp/dbget-bin/www_bget?pathway:",
                                    sub("[^:]*:", '', kegg_pathway_info$pathway),
                                    sep='')

    # Kegg gives pathways to us in its own IDs, we first need to convert those to NCBI/Entrez gene ids
    kegg_to_ncbi <- keggConv(kegg.species, "ncbi-geneid");
    kegg_to_ncbi <- data.frame(list("kegg_geneid"=unname(kegg_to_ncbi), "ncbi_geneid"=names(kegg_to_ncbi)));
    kegg_pathways_ncbi <- kegg_pathways %>%
        left_join(kegg_to_ncbi) %>%
        select(c("ncbi_geneid", "pathway"));

    # Convert NCBI/Entrez gene ids to Ensembl IDs
    mart <- useDataset(paste(species, "_gene_ensembl", sep=''), ensembl_mart);
    ncbi_to_ensembl <- getBM(attributes=c("ensembl_gene_id", "entrezgene_id"), mart=mart);
    ncbi_to_ensembl$ncbi_geneid = paste("ncbi-geneid:", ncbi_to_ensembl$entrezgene_id, sep='');
    kegg_pathways_ensembl <- kegg_pathways_ncbi %>%
        left_join(ncbi_to_ensembl) %>%
        select(c("ensembl_gene_id", "pathway"))  %>%
        drop_na();

    # Output as JSON
    objectified <- kegg_pathways_ensembl %>%
        group_by(pathway) %>%
        summarise(feature_ids = list(ensembl_gene_id),) %>%
        left_join(kegg_pathway_info);
    write_json(objectified, paste(work.dir, "/static/json/", species, ".ensembl_gene_id.KEGG.pathways.json", sep=''));
}
