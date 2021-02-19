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
                search_pattern: '',
            },
        };
    },


    props: {
        "background": Array,
        "foreground": Array,
    },

    methods:{
        "runPathwayAnalysis": function() {
            let tests =  test_pathways(this.foreground, this.background, this.pathways);
            let results = tests['results'].sort( function(p1, p2) {
                return p1.p - p2.p;
            });
            results.forEach( function (result) {
                if (result.name === undefined) {
                    result.name = "Unkown Pathway";
                }
            });
            // Freeze it so that it's non-reactive.
            // Adding reactivity is too slow
            Object.freeze(results);
            this.results = results;

            this.used_background = tests.background;
            this.used_foreground = tests.foreground;
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
                ["foreground_size",  this.used_foreground.size],
                ["background_size",  this.used_background.size],
                ["pathway",  Array.from(pathway.feature_ids)],
                ["foreground",  Array.from(this.used_foreground)],
                ["intersection",  Array.from(pathway.feature_ids).filter(function(x) { return vm.used_foreground.has(x);})],
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
            let pattern = this.config.search_pattern.toUpperCase();
            return this.results.filter(function(x) {
                return x.name.toUpperCase().includes(pattern);
            }).slice(0,10);
        },

        pathways: function() {
            // Pathways that have been restricted to our background set
            console.log("Re-restricting pathways");
            let pathways = restrict_pathways(this.full_pathways, this.background)
            Object.preventExtensions(pathways); // Contents aren't reactive
            return pathways;
        },
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
            fetch(db_data.url+"?v="+Math.random())
                .then(function(res) {return res.json()})
                .then(function(res) {
                    Object.preventExtensions(res); // Contents aren't reactive
                    vm.full_pathways = res;
                })
                .catch(function(err){
                    console.log("ERROR loading pathways ", err);
                });
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
