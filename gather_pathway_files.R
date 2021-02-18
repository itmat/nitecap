library(biomaRt);
library(dplyr);
library(jsonlite);

species.list <- c("mmusculus", "hsapiens", "dmelanogaster");
kegg.species.list <- c("mmu", "hsa", "dme");
id_types <- c("ensembl_gene_id"); #TODO: to include any different ID types, we would have to update the group_by function
ensembl_mart <- useMart("ensembl");

# Use this to check the avialable datasets (to find species)
#datasets <- listDatasets(mart);

# Load the child-parent GO ontology relationships
# Table of child->parent relationships mapping GO id's to each other
go_parents <- read.table("C:/Users/tgb/nitecap/processed_obo.txt", sep="\t", header=TRUE);

# GO term definitions
go_definitions <- read.table("C:/Users/tgb/nitecap/go_definitions.txt", sep="\t", header=TRUE, quote="");

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
        objectified$url = paste("https://www.ebi.ac.uk/QuickGO/term/", objectified$pathway);

        write_json(objectified, paste("C:/Users/tgb/nitecap/static/json/", species, ".", id_type, ".GO.pathways.json", sep=''));
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


    kegg_to_ncbi <- keggConv(kegg.species, "ncbi-geneid");
    kegg_to_ncbi <- data.frame(list("kegg_geneid"=unname(kegg_to_ncbi), "ncbi_geneid"=names(kegg_to_ncbi)));
    kegg_pathways_ncbi <- kegg_pathways %>%
        left_join(kegg_to_ncbi) %>%
        select(c("ncbi_geneid", "pathway"));

    mart <- useDataset(paste(species, "_gene_ensembl", sep=''), ensembl_mart);
    ncbi_to_ensembl <- getBM(attributes=c("ensembl_gene_id", "entrezgene_id"), mart=mart);
    ncbi_to_ensembl$ncbi_geneid = paste("ncbi-geneid:", ncbi_to_ensembl$entrezgene_id, sep='');
    kegg_pathways_ensembl <- kegg_pathways_ncbi %>%
        left_join(ncbi_to_ensembl) %>%
        select(c("ensembl_gene_id", "pathway"))  %>%
        drop_na();

    objectified <- kegg_pathways_ensembl %>%
        group_by(pathway) %>%
        summarise(feature_ids = list(ensembl_gene_id),) %>%
        left_join(kegg_pathway_info);
    write_json(objectified, paste("C:/Users/tgb/nitecap/static/json/", species, ".ensembl_gene_id.KEGG.pathways.json", sep=''));
}
