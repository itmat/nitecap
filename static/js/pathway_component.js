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
                "Ensembl_Homology_GO_MMusculus": {
                    url: "/static/json/mmusculus.ensembl_gene_id.GO.homology_pathways.json",
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
                "Ensembl_Homology_GO_DMelanogaster": {
                    url: "/static/json/dmelanogaster.ensembl_gene_id.GO.homology_pathways.json",
                    species: "Drosophila melanogaster",
                    id_types: "Ensembl Genes",
                    pathways: "GO",
                },
            },
            results: [],
            full_pathways: [],
            used_background: [], // Background list used in latest analysis
            used_foreground: [], // Foreground list used in latest analysis
            config: {
                database_id: "none",
                continuous: false,
                MAX_PATHWAY_NAME_LENGTH: 45,
                MAX_PATHWAY_SIZE: 10000,
                MIN_PATHWAY_SIZE: 10,
                search_pattern: '',
            },
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
        "background": Array,
        "foreground": Array,
    },

    methods:{
        "runPathwayAnalysis": function() {
            // Grab but don't use pathways
            // this forces them to be recomputed and set to worker
            let pathways = this.pathways; 

            let message = {
                type: "run_analysis",
                foreground: this.foreground,
                background: this.background,
            };
            let state = {
                message: message,
                pathways: this.pathways,
                foreground: this.foreground,
                background: this.background,
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

        download_top_pathway: function(i) {
            // Prepare and download 1 pathway result
            let vm = this;
            let pathway = this.top_pathways[i];
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
        top_pathways: function() {
            // Top results from pathway analysis
            let results = this.results;
            let pattern = this.config.search_pattern.toUpperCase();
            if (pattern != '') {
                results = results.filter(function(x) {
                    return x.name.toUpperCase().includes(pattern);
                })
            }
            return results.slice(0,10);
        },

        pathways: function() {
            let vm = this;
            // Pathways that have been restricted to our background set
            console.log("Re-restricting pathways");
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
            console.log("Messaging worker...");
            return pathways;
        },
    },

    created: function() {
        let vm = this;
        vm.worker = new Worker('/static/js/pathway_worker.js');
        vm.worker.onmessage = function(message) {
            console.log("Received message: ", message.data);
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
            fetch(db_data.url)
                .then(function(res) {return res.json()})
                .then(function(res) {
                    Object.preventExtensions(res); // Contents aren't reactive
                    vm.full_pathways = res;
                })
                .catch(function(err){
                    console.log("ERROR loading pathways ", err);
                });
        },

        "full_pathways": function() {
            let vm = this;
            if (vm.full_pathways != [] && vm.config.continuous) {
                this.runPathwayAnalysis();
            }
        },

        "foreground": function() {
            let vm = this;
            if (vm.full_pathways != [] && vm.config.continuous) {
                this.runPathwayAnalysis();
            }
        },

        "config.continuous": function() {
            let vm = this;
            if (vm.full_pathways != [] && vm.config.continuous) {
                this.runPathwayAnalysis();
            }
        },
    },

    template: `<div class="card">
        <div class="card-header">
            Pathway Analysis
            <a id="PathwayAnalysisHelp" class="text-primary help-pointer ml-3"
               data-container="body" data-toggle="popover" data-placement="top" data-trigger="click"
               title="Pathway Analysis Help"
               data-content="Run pathway analysis using the genes selected above. Choose a dataset of pathways first. Filtered genes are removed from the background.">
                <i class="fas fa-info-circle"></i>
            </a>
        </div>

        <div class="card-body">
            <div class="form-check form-inline">
                <label class="form-check-label" for="database_id_selector">Pathway Database</label>
                <select name="database_id_selector" id="database_id_selector" v-model="config.database_id">
                    <option 
                        v-for="(db, db_id) in all_databases"
                        v-bind:value="db_id">
                        {{db_id}}
                    </option>
                </select>

                <button class="btn btn-primary m-3"
                    v-on:click="runPathwayAnalysis"
                    v-bind:disabled="full_pathways.length == 0">
                    Run Pathway Analysis
                </button>
                <input class="form-check-input" id="run_continuously" type="checkbox" v-model="config.continuous">
                <label class="form-check-label" for="run_continuously">Update continuously</label>


            </div>

            <div>
                <table class="table table-sm" v-if="top_pathways.length > 0">
                    <thead>
                    <tr> <th scope="col">Name</th> <th scope="col">p-Value</th> <th>Overlap</th> <th>Pathway Size</th> <th>Download</th> </tr>
                    </thead>
                    <tbody is="transition-group" name="swap-list">
                        <tr v-for="(pathway,i) in top_pathways" v-bind:key="pathway.pathway" class="swap-list-item">
                            <td><a v-bind:href="pathway.url">{{ pathway.name.slice(0,this.MAX_PATHWAY_NAME_LENGTH) }}</a></td>
                            <td>{{util.formatNum(pathway.p, 4)}} </td>
                            <td>{{pathway.overlap}} </td>
                            <td>{{pathway.pathway_size}} </td>
                            <td> <button v-on:click="download_top_pathway(i)" type="button" class="btn btn-secondary btn-sm" >Download</button></td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="form-inline">
                <label for="results_search">Search</label>
                <input class="form-control form-control-sm ml-2" type="text" name="results_search"
                       placeholder="Search for pathways" v-model="config.search_pattern"
                       />
                <button v-on:click="download_pathway_results" type="button" class="btn btn-secondary btn-sm ml-5" >Download Results</button>
            </div>
        </div>
    </div>`,
});
