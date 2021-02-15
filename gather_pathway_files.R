library(biomaRt);
library(dpylr);
library(jsonlite);

species.list <- c("mmusculus", "hsapiens", "dmelanogaster");
id_types <- c("ensembl_gene_id"); #TODO: to include any different ID types, we would have to update the group_by function
ensembl_mart <- useMart("ensembl");

# Use this to check the avialable datasets (to find species)
#datasets <- listDatasets(mart);

for (species in species.list) {
    mart <- useDataset(paste(species, "_gene_ensembl", sep=''), ensembl_mart);
    for (id_type in id_types) {
        bm <- getBM(attributes=c(id_type, "go_id", "name_1006", "definition_1006", "namespace_1003"), mart=mart);

        objectified <- bm %>%
            rename(
                name = name_1006,
                definition = definition_1006,
                go_namespace = namespace_1003) %>%
            filter(
                go_id != ""
                ) %>%
            group_by(go_id, name, definition, go_namespace) %>%
            summarise(
                feature_ids = list(ensembl_gene_id),
                )
        write_json(objectified, paste("C:/Users/tgb/nitecap/static/json/", species, ".", id_type, ".GO.pathways.json", sep=''));
    }
}
