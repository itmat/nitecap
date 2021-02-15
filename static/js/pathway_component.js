Vue.component( 'pathway-analysis', {
    data: function () {
        return {
            all_databases: {
                "Ensembl_GO_HSapiens": {
                    url: "/static/json/hsapiens.ensembl_gene_id.GO.pathways.json",
                    species: "Mus musculus",
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
                    species: "Mus musculus",
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
            },
        };
    },


    props: {
        "background": Array,
        "foreground": Array,
    },

    methods:{
        "runPathwayAnalysis": function() {
            let background = this.background;
            let foreground = this.foreground.filter(function(x) {
                return (background.indexOf(x) >= 0);
            });
            let analysis =  test_pathways(foreground, background, this.pathways);
            this.results = analysis.sort( function(p1, p2) {
                return p1.p - p2.p;
            });
        },

    },

    computed: {
        top_pathways: function() {
            // Top results from pathway analysis
            return this.results.slice(0,10);
        },

        pathways: function() {
            // Pathways that have been restricted to our background set
            return restrict_pathways(this.full_pathways, this.background)
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
                    <tr> <th scope="col">Name</th> <th scope="col">p-Value</th> <th>Overlap</th> <th>Pathway Size</th> </tr>
                    </thead>
                    <tbody is="transition-group" name="swap-list">
                        <tr v-for="pathway in top_pathways" v-bind:key="pathway.name" class="swap-list-item">
                            <td><a v-bind:href="'https://www.ebi.ac.uk/QuickGO/term/'+pathway.go_id">{{ pathway.name.slice(0,this.MAX_PATHWAY_NAME_LENGTH) }}</a></td>
                            <td>{{util.formatNum(pathway.p, 4)}} </td>
                            <td>{{pathway.overlap}} </td>
                            <td>{{pathway.pathway_size}} </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>`,
});
