Vue.component("heatmap-plot", { 
    data: function () {
        return {
            FONT_SIZE: 16,
            cutoff: 0,
            rendered: false,
            data: [],
            x_values: [],
            x_labels: [],
            heatmap_labels: [],
            config: {
                fold_days: false,
                combine_replicates: false,
                show_labels: false,
            },
        };
    },

    props: {
        spreadsheets: Array,
        descriptive_names: Array,
        num_days: Number,
        selected_rows: Array,
        labels: Array,
        timepoint_labels: Array,
        day_and_time_labels: Array,
        sort_by_spreadsheet: Number,
    },

    methods: {
        updateHeatmap: function() {
            let vm = this;

            vm.cutoff = vm.selected_rows.length;

            if (vm.spreadsheets[vm.sort_by_spreadsheet].jtk_lag == null) {
                let error_message = "Error: Heatmap generated before JTK Lag value was complete. Ordering the heatmap requires phase values, so the computation must finish first.";

                let nitecap_error = $("#error-modal");
                let nitecap_error_message = $("#error-modal-message")
                nitecap_error_message.text(error_message);
                nitecap_error.modal();
                return;
            }


            let phase_sorted_order = vm.selected_rows.sort( function (i,j) {
                return compare(
                            vm.spreadsheets[vm.sort_by_spreadsheet].jtk_lag[i],
                            vm.spreadsheets[vm.sort_by_spreadsheet].jtk_lag[j],
                            i,j);
            } );

            let zScoreData = vm.spreadsheets.map(function(spreadsheet) {
                return computeZScores(phase_sorted_order)(spreadsheet.data);
            });

            let times = vm.spreadsheets.map(function(spreadsheet){ return spreadsheet.x_values; });

            if (vm.config.fold_days) {
                times = vm.spreadsheets.map(function(spreadsheet) {
                    return spreadsheet.x_values.map(function(x) {
                        return x % spreadsheet.timepoints_per_cycle;
                    });
                });
            }

            vm.heatmap_labels = phase_sorted_order.map( function(i) {
                return vm.labels[i];
            } );

            let heatmap_options = {
                modeBarButtonsToAdd: [{
                    name: 'download in SVG format',
                    icon: Plotly.Icons.camera,
                    click: function (gd) {
                        Plotly.downloadImage(gd, {format: 'svg'})
                    }
                }]
            };

            if (vm.config.combine_replicates) {
                // Average all z-scores at the same timepoint together
                let meanZScores = zScoreData.map( function(zscores,idx) {
                    return meanByTimepoints(zscores, times[idx]);
                });

                vm.data = meanZScores;

                if (vm.config.fold_days) {
                    vm.x_values = vm.timepoint_labels.map( function(array, idx) {
                        return array.slice(0,vm.spreadsheets[idx].timepoints_per_cycle);
                    });
                } else {
                    vm.x_values = vm.day_and_time_labels;
                }
            } else {
                if (vm.config.fold_days) {
                    let x_sort_order = times.map( function(times_) {
                        return times_.map( function(x,i) {return i;} ).sort( function (i,j) {
                            return compare(times_[i],times_[j],i,j);
                        } );
                    });

                    vm.data = zScoreData.map( function(zscores,idx) {
                        return zscores.map( function(row) {
                            return x_sort_order[idx].map( function(i) {
                                return row[i];
                            });
                        } );
                    });

                    vm.x_values = x_sort_order.map( function(x_sort_order_, idx) {
                        let times_ = times[idx];
                        return x_sort_order_.map( function(i) {
                            return vm.timepoint_labels[idx][times_[i]];
                        });
                    });
                } else {
                    vm.data = zScoreData;

                    vm.x_values = vm.spreadsheets.map( function(spreadsheet, idx) {
                        let rep_counts = [];
                        return spreadsheet.x_values.map( function(time) {

                            return vm.day_and_time_labels[idx][time];
                        });
                    });
                }
            }

            // Find max/min values so that we can center the colormap with 0=middle
            let maxInRow = vm.data.map( function(spreadsheet) { return spreadsheet.map(array_max); });
            let minInRow = vm.data.map( function(spreadsheet) { return spreadsheet.map(array_min); });

            let max = array_max(maxInRow.map(array_max));
            let min = array_min(minInRow.map(array_min));
            let limit = Math.max(Math.abs(min), Math.abs(max));

            let y_vals =  vm.heatmap_labels.map(function (x,i) {return i;});

            let heatmap_values = vm.spreadsheets.map( function(spreadsheet, idx) {
                let colorbar = {};
                if (idx === 0){
                    colorbar = {
                        title: 'Z Score',
                        titleside: 'right'
                    };
                }
                return {
                    x: vm.x_values[idx].map(function (x,i) { return i; }),
                    y: y_vals,
                    z: vm.data[idx],
                    type: 'heatmap',
                    xaxis: "x" + (idx+1),
                    yaxis: "y",
                    zmin: -1 * limit,
                    zmax: limit,
                    colorbar: colorbar,
                };
            });

            let heatmap_layout = {
                height: 700,
                width: 300*vm.spreadsheets.length+200*vm.config.show_labels+500,
                margin: {
                    l: 100+200*vm.config.show_labels,
                    r: 5,
                    b: 175,
                    t: 50
                },
                font: {
                    size: FONT_SIZE,
                },
                pad: 4,
                yaxis: {
                    tickmode: "array",
                    ticktext: vm.heatmap_labels,
                    tickvals: y_vals,
                    showticklabels: vm.config.show_labels,
                    ticks: ''
                },
                grid: {
                    rows: 1,
                    columns: vm.spreadsheets.length,
                },
            };
            vm.spreadsheets.forEach(function(spreadsheet, idx) {
                let idx_suffix = (idx>0) ? (idx+1) : '';
                heatmap_layout['xaxis'+idx_suffix] = {
                    tickmode: 'array',
                    tickvals: vm.x_values[idx].map(function (x,i) { return i; }),
                    ticktext: vm.x_values[idx],
                };
            });

            Plotly.newPlot('heatmap', heatmap_values, heatmap_layout, heatmap_options);

            // Manually add in the titles to the subplots
            // since Plotly.js does not support this
            let d3_top = Plotly.d3.select("#heatmap");
            vm.spreadsheets.forEach(function(spreadsheet, idx) {
                let plot_idx = idx === 0 ? '' : idx + 1;
                let subplot = d3_top.select(".x"+(plot_idx)+"y");
                let subplot_rect = subplot.select("rect")[0][0];
                let mid_point = subplot_rect.x.baseVal.value + subplot_rect.width.baseVal.value/2;
                let top = subplot_rect.y.baseVal.value;

                let t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                t.setAttribute('x', ''+mid_point);
                t.setAttribute('y', '40');
                t.setAttribute('fill', '#000');
                t.setAttribute('text-anchor', 'middle');
                t.textContent = vm.descriptive_names[idx];
                subplot[0][0].appendChild(t);
            });

            vm.rendered = true;
        },

        downloadHeatmap: function(format) {
            let gd = document.getElementById('heatmap');
            Plotly.downloadImage(gd, {format: format, filename: 'heatmap_' + (this.selected_rows.length)});
        },
    },

    watch: {
        "config": {
            handler: "updateHeatmap",
            deep: true
        },
    },
    
    template:` 
        <div>
            <button class="btn btn-primary" v-on:click="updateHeatmap">Generate Heatmap</button>
            <div v-show="rendered">
                <div id="heatmap"></div>
                <div class="form-group form-inline">
                    <div class="form-check mx-3">
                        <input class="form-check-input" id="combine_replicates" type="checkbox" v-model="config.combine_replicates">
                        <label class="form-check-label" for="combine_replicates">Combine replicates</label>
                    </div>

                    <div class="form-check mx-3" v-if="num_days > 1">
                        <input class="form-check-input" id="heatmap_fold_days" type="checkbox" v-model="config.fold_days">
                        <label class="form-check-label" for="heatmap_fold_days">Overlay cycles</label>
                    </div>

                    <div class="form-check mx-3">
                        <input class="form-check-input" id="heatmap_show_labels" type="checkbox" v-model="config.show_labels">
                        <label class="form-check-label" for="heatmap_show_labels">Show row labels</label>
                    </div>
                </div>
                <span class="dropdown">
                    <button class="btn btn-primary btn-sm dropdown-toggle" id="download_heatmap" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                        Download Plot
                    </button>
                    <div class="dropdown-menu" aria-labelledby="download_heatmap">
                        <button class="dropdown-item" v-on:click="downloadHeatmap('png')">PNG</button>
                        <button class="dropdown-item" v-on:click="downloadHeatmap('svg')">SVG</button>
                    </div>
                </span>
                <span>Number of items in heatmap: {{heatmap_labels.length}}</span>
            </div> 
        </div>
    `,
});