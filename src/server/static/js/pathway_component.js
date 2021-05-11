Vue.component( 'pathway-analysis', {
    data: function () {
        return {
            all_databases: {
                "Ensembl_KEGG_HSapiens": {
                    url: "/static/json/hsapiens.ensembl_gene_id.KEGG.pathways.json",
                    species: "Homo sapiens",
                    pathways: "KEGG",
                },
                "Ensembl_KEGG_MMusculus": {
                    url: "/static/json/mmusculus.ensembl_gene_id.KEGG.pathways.json",
                    species: "Mus musculus",
                    pathways: "KEGG",
                },
                "Ensembl_KEGG_DMelanogaster": {
                    url: "/static/json/dmelanogaster.ensembl_gene_id.KEGG.pathways.json",
                    species: "Drosophila melanogaster",
                    pathways: "KEGG",
                },

                "NCBI_KEGG_HSapiens": {
                    url: "/static/json/hsapiens.ncbi_gene_id.KEGG.pathways.json",
                    species: "Homo sapiens",
                    pathways: "KEGG",
                },
                "NCBI_KEGG_MMusculus": {
                    url: "/static/json/mmusculus.ncbi_gene_id.KEGG.pathways.json",
                    species: "Mus musculus",
                    pathways: "KEGG",
                },
                "NCBI_KEGG_DMelanogaster": {
                    url: "/static/json/dmelanogaster.ncbi_gene_id.KEGG.pathways.json",
                    species: "Drosophila melanogaster",
                    pathways: "KEGG",
                },

                "Ensembl_GO_HSapiens": {
                    url: "/static/json/hsapiens.ensembl_gene_id.GO.pathways.json",
                    species: "Homo sapiens",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },
                "Ensembl_GO_MMusculus": {
                    url: "/static/json/mmusculus.ensembl_gene_id.GO.pathways.json",
                    species: "Mus musculus",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },
                "Ensembl_GO_DMelanogaster": {
                    url: "/static/json/dmelanogaster.ensembl_gene_id.GO.pathways.json",
                    species: "Drosophila melanogaster",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },

                "NCBI_GO_HSapiens": {
                    url: "/static/json/hsapiens.entrezgene_id.GO.pathways.json",
                    species: "Homo sapiens",
                    id_types: "NCBI Genes",
                    pathways: "GO",
                },
                "NCBI_GO_MMusculus": {
                    url: "/static/json/mmusculus.entrezgene_id.GO.pathways.json",
                    species: "Mus musculus",
                    id_types: "NCBI Genes",
                    pathways: "GO",
                },
                "NCBI_GO_DMelanogaster": {
                    url: "/static/json/dmelanogaster.entrezgene_id.GO.pathways.json",
                    species: "Drosophila melanogaster",
                    id_types: "NCBI Genes",
                    pathways: "GO",
                },

                "GeneSymbol_GO_HSapiens": {
                    url: "/static/json/hsapiens.external_gene_name.GO.pathways.json",
                    species: "Homo sapiens",
                    id_types: "GeneSymbol Genes",
                    pathways: "GO",
                },
                "GeneSymbol_GO_MMusculus": {
                    url: "/static/json/mmusculus.external_gene_name.GO.pathways.json",
                    species: "Mus musculus",
                    id_types: "GeneSymbol Genes",
                    pathways: "GO",
                },
                "GeneSymbol_GO_DMelanogaster": {
                    url: "/static/json/dmelanogaster.external_gene_name.GO.pathways.json",
                    species: "Drosophila melanogaster",
                    id_types: "GeneSymbol Genes",
                    pathways: "GO",
                },

                "Ensembl_Homology_GO_MMusculus": {
                    url: "/static/json/mmusculus.ensembl_gene_id.GO.homology_pathways.json",
                    species: "Mus musculus",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },
                "Ensembl_Homology_GO_DMelanogaster": {
                    url: "/static/json/dmelanogaster.ensembl_gene_id.GO.homology_pathways.json",
                    species: "Drosophila melanogaster",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },
            },

            results: [],
            full_pathways: [],
            config: {
                database_id: "none",
                continuous: false,
                MAX_PATHWAY_NAME_LENGTH: 45,
                MAX_PATHWAY_SIZE: 10000,
                MIN_PATHWAY_SIZE: 10,
                search_pattern: '',
                num_pathways_shown: 10,
                top_pathway_shown: 0,
                remove_unannotated: true, // Background to only include genes in at least one pathway
                selected_id_column: 0,
            },
            loading_resources: false,
            worker: null,
            worker_busy: false,
            // next message to send the worker when not busy
            // only ever queue up to 1 message, just discard any others
            queued_state: null,
            // The values we're currently working with
            running_state: null,
            // The state used for the last results obtained
            last_ran_state: null,
        };
    },


    props: {
        "background_rows": Array,
        "selected_rows": Array,
        "ids": Array,
        "id_labels": Array,
    },

    methods:{
        "runPathwayAnalysis": function() {
            // Nothing to run yet
            if (this.full_pathways.length < 0) { return; }

            // Grab but don't use pathways
            // this forces them to be recomputed and set to worker
            let pathways = this.pathways;

            let background = this.background;
            if (this.config.remove_unannotated) {
                background = this.reduced_background;
            }

            let message = {
                type: "run_analysis",
                foreground: this.foreground,
                background: background,
            };
            let state = {
                message: message,
                pathways: this.pathways,
                foreground: this.foreground,
                background: background,
            };
            Object.freeze(state);// non-reactive
            Object.freeze(message);// non-reactive

            if (!this.worker_busy) {
                this.worker.postMessage(message);
                this.worker_busy = true;
                this.running_state = state;
            } else {
                this.queued_state = state;
            }
        },

        download_shown_pathway: function(i) {
            // Prepare and download 1 pathway result
            let vm = this;
            let pathway = this.shown_pathways[i];
            let results = [
                ["pathway",  pathway.pathway],
                ["pathway_name",  pathway.name],
                ["pathway_url",  pathway.url],
                ["pathway_size",  pathway.feature_ids.size],
                ["foreground_size",  this.last_run_state.foreground.size],
                ["background_size",  this.last_runn_state.background.size],
                ["pathway",  Array.from(pathway.feature_ids)],
                ["foreground",  Array.from(this.last_run_state.foreground)],
                ["intersection",  Array.from(pathway.feature_ids).filter(function(x) { return vm.last_run_state.foreground.has(x);})],
            ];
            // Generate tab-separated file containing the info
            let result_tsv = results.map(function (entries) {
                let name = entries[0];
                let value = entries[1];
                if (Array.isArray(value)) {
                    value = value.join("\t");
                }
                return name + "\t" + value
            }).join('\n');


            let el = document.createElement('a');
            el.setAttribute('href', 'data:text/plain;charset=utf-8,'  + encodeURIComponent(result_tsv));
            el.setAttribute('download', "pathway_results."+pathway.pathway+".txt");
            el.style.display='none';
            document.body.appendChild(el);
            el.click();
            document.body.removeChild(el);
        },

        download_pathway_results: function(i) {
            // Prepare and download pathway result summary
            let vm = this;
            let values = ["pathway", "name", "url", "p", "overlap", "pathway_size", "selected_set_size", "background_size"];
            // Generate tab-separated file containing the info
            let header = values.join('\t') + '\n';
            let result_tsv = header + vm.results.map(function (result) {
                return values.map(function(val) { return result[val]; }).join('\t');
            }).join('\n');


            let el = document.createElement('a');
            el.setAttribute('href', 'data:text/plain;charset=utf-8,'  + encodeURIComponent(result_tsv));
            el.setAttribute('download', "pathway_results.txt");
            el.style.display='none';
            document.body.appendChild(el);
            el.click();
            document.body.removeChild(el);
        },

    },

    computed: {
        shown_pathways: function() {
            // Top results from pathway analysis
            let results = this.results;
            let pattern = this.config.search_pattern.toUpperCase();
            if (pattern != '') {
                results = results.filter(function(x) {
                    return x.name.toUpperCase().includes(pattern);
                })
            }

            // Gather the slice of the currently visible pathways
            let [top, bottom] = this.shown_pathways_slice;
            return results.slice(top, bottom);
        },

        shown_pathways_slice: function () {
            let top = Math.max(0, Math.min( this.results.length - this.config.num_pathways_shown, this.config.top_pathway_shown));

            let bottom = Math.min(this.results.length, top + this.config.num_pathways_shown);
            return [top, bottom];
        },

        pathways: function() {
            let vm = this;
            // Pathways that have been restricted to our background set
            let pathways = restrict_pathways(this.full_pathways, this.background)

            // Further filter out pathways with extreme size
            pathways = pathways.filter(function(pathway) {
                return ((pathway.feature_ids.size >= vm.config.MIN_PATHWAY_SIZE) &&
                        (pathway.feature_ids.size <= vm.config.MAX_PATHWAY_SIZE));
            });

            // Convert to a Map
            pathways = new Map(pathways.map(function(pathway) {
                return [pathway.pathway, pathway];
            }));
            Object.freeze(pathways); // Contents aren't reactive

            // Send pathways to the worker thread
            this.worker.postMessage({
                type: "set_pathways",
                pathways: pathways,
            });
            return pathways;
        },

        all_genes_in_pathways: function() {
            let vm = this;
            let ids_union = new Set();
            vm.pathways.forEach(function(pathways) {
                pathways.feature_ids.forEach(function(id) {
                    ids_union.add(id);
                });
            });
            return ids_union;
        },

        background: function() {
            let vm = this;
            return vm.background_rows.map( function(i) {
                // Convert id to string if necessary
                return ''+vm.ids[vm.config.selected_id_column][i];
            });

        },

        reduced_background: function() {
            let vm = this;
            let background = vm.background;

            let all_genes_in_pathway = vm.all_genes_in_pathways;
            return background.filter(function(gene) {
                return all_genes_in_pathway.has(gene);
            });
        },

        foreground: function() {
            let vm = this;
            let foreground = vm.selected_rows.map(function(i) {
                // Convert id to string if necessary
                return ''+vm.ids[vm.config.selected_id_column][i];
            });

            let all_genes_in_pathway = vm.all_genes_in_pathways;
            return foreground.filter(function(gene) {
                return all_genes_in_pathway.has(gene);
            });
        },
    },

    created: function() {
        let vm = this;
        vm.worker = new Worker('/static/js/pathway_worker.js');
        vm.worker.onmessage = function(message) {
            vm.last_run_state = vm.running_state;

            let results = message.data.results;
            results.forEach( function (result) {
                let pathway = vm.running_state.pathways.get(result.pathway);
                Object.assign(result, pathway);
                Object.assign(result, {
                    background_size: vm.last_run_state.background.size,
                    selected_set_size: vm.last_run_state.foreground.size,
                    pathway_size: pathway.feature_ids.size,
                });
                if (result.name === undefined) {
                    // Give names to unknown pathways that are just their IDs
                    result.name = result.pathway || "unknown pathway";
                }
            });
            Object.freeze(results);
            vm.results = results;
            vm.last_ran_state = vm.running_state;
            vm.running_state = null;

            vm.worker_busy = false;

            if (vm.queued_state !== null) {
                // Finished the previous message, now do the queued one
                vm.worker.postMessage(vm.queued_state.message);
                vm.running_state = vm.queued_state;
                vm.queued_state = null;
                vm.worker_busy = true;
            }
        };
    },

    watch: {
        "config.database_id": function () {
            let vm = this;

            // Clear any existing pathways loaded
            vm.full_pathways = [];

            // Nothing chosen, done
            if (vm.config.database_id == "none") {
                return;
            }

            // Load the new pathways
            let db_data = vm.all_databases[vm.config.database_id];
            vm.loading_resources = true;
            fetch(db_data.url)
                .then(function(res) {return res.json()})
                .then(function(res) {
                    Object.preventExtensions(res); // Contents aren't reactive
                    // Convert the feature ids to strings (eg: for NCBI which are integers)
                    res.forEach(function(pathway) {
                        pathway.feature_ids = pathway.feature_ids.map( function(x) {
                            return ''+x;
                        });
                    });
                    vm.full_pathways = res;
                    vm.loading_resources = false;
                })
                .catch(function(err){
                    console.log("ERROR loading pathways ", err);
                    vm.loading_resources = true;
                });
        },

        "full_pathways": function () {
            if (this.config.continuous) { this.runPathwayAnalysis(); }
        },
        "selected_rows": function () {
            if (this.config.continuous) { this.runPathwayAnalysis(); }
        },
        "config.continuous": function () {
            if (this.config.continuous) { this.runPathwayAnalysis(); }
        },
        "config.remove_unannotated": function () {
            if (this.config.continuous) { this.runPathwayAnalysis(); }
        },
    },

    template: `
        <div>
            <div class="form-check form-inline">
                <label class="form-check-label" for="database_id_selector">Pathway Database</label>
                <select name="database_id_selector" id="database_id_selector" v-model="config.database_id">
                    <option
                        v-for="(db, db_id) in all_databases"
                        v-bind:value="db_id">
                        {{db_id}}
                    </option>
                </select>

                <label v-show="id_labels.length > 1"class="form-check-label" for="id_column_selector">ID Column</label>
                <select v-show="id_labels.length > 1"name="id_column_selected" id="id_column_selector" v-model="config.selected_id_column">
                    <option
                        v-for="(id_col, index) in id_labels"
                        v-bind:value="index">
                        {{id_col}}
                    </option>
                </select>

                <button class="btn btn-primary m-3"
                    v-on:click="runPathwayAnalysis"
                    v-bind:disabled="full_pathways.length == 0">
                    Run Pathway Analysis
                    <span v-if="loading_resources" class='spinner-border spinner-border-sm text-light mr-2' role='status' aria-hidden='true'> </span>
                </button>
                <a id="PathwayAnalysisHelp" class="text-primary help-pointer ml-1"
                   data-container="body" data-toggle="popover" data-placement="top" data-trigger="click"
                   title="Pathway Analysis Help"
                   data-content="Run pathway analysis using the genes selected above. Choose a dataset of pathways first. Filtered genes are removed from the background. If updating continuously, any change to the selected gene set will automatically recompute pathways. If removing unannotated genes, any genes will be dropped from the analysis if they appear in no pathways.">
                    <i class="fas fa-info-circle"></i>
                </a>
            </div>

            <div class="row">
                <div class="col">
                    <div class="form-check form-inline">
                        <input class="form-check-input" id="run_continuously" type="checkbox" v-model="config.continuous">
                        <label class="form-check-label" for="run_continuously">Update continuously</label>
                        <input class="form-check-input ml-2" id="remove_unannotated" type="checkbox" v-model="config.remove_unannotated">
                        <label class="form-check-label" for="remove_unannotated">Remove unannotated genes</label>
                    </div>
                </div>
            </div>

            <div v-if="shown_pathways.length > 0">
                <table class="table table-sm">
                    <thead>
                    <tr> <th scope="col">Name</th> <th scope="col">p-Value</th> <th>Overlap</th> <th>Pathway Size</th> <th>Download</th> </tr>
                    </thead>
                    <tbody is="transition-group" name="swap-list">
                        <tr v-for="(pathway,i) in shown_pathways" v-bind:key="i" class="swap-list-item">
                            <td style="width: 51%"><a v-bind:href="pathway.url">{{ pathway.name.slice(0,this.MAX_PATHWAY_NAME_LENGTH) }}</a></td>
                            <td style="width: 12%">{{util.formatNum(pathway.p, 4)}} </td>
                            <td style="width: 12%">{{pathway.overlap}} </td>
                            <td style="width: 12%">{{pathway.pathway_size}} </td>
                            <td style="width: 12%"> <button v-on:click="download_shown_pathway(i)" type="button" class="btn btn-secondary btn-sm" >Download</button></td>
                        </tr>
                    </tbody>
                </table>
                <div class="row">
                    <div class="col">
                        Foreground size: {{last_ran_state.foreground.length}}
                        Background size: {{last_ran_state.background.length}}
                    </div>
                </div>

            </div>

            <div v-if="shown_pathways.length == 0">
                <!-- error/status messages for when no pathway results -->
                <div v-if="reduced_background.length == 0" class="alert alert-warning">
                    No genes identifiers are shared between pathway list and given spreadsheet(s).
                    Do the species and ID type match the chosen pathway list?
                </div>
            </div>

            <div class="form-inline">
                <label for="results_search">Search</label>
                <input class="form-control form-control-sm ml-2" type="text" name="results_search"
                       placeholder="Search for pathways" v-model="config.search_pattern"
                       />
                <button v-on:click="download_pathway_results" type="button" class="btn btn-secondary btn-sm ml-5" >Download Results</button>

                <button v-on:click="config.top_pathway_shown = shown_pathways_slice[0] - config.num_pathways_shown" type="button" class="btn btn-secondary btn-sm ml-5" >&lt;</button>
                {{shown_pathways_slice[0]+1}} - {{shown_pathways_slice[1]}}
                <button v-on:click="config.top_pathway_shown = shown_pathways_slice[0] + config.num_pathways_shown" type="button" class="btn btn-secondary btn-sm" >&gt;</button>
            </div>

        </div>`,
});