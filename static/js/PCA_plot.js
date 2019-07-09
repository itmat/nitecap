Vue.component('pca-plot', {
    data: function () {
        return {
            PCA_WIDTH: 800,
            PCA_HEIGHT: 800,
            PCA_SYMBOL: "M 0,-15 A 15,15 0 0,1 15,0 L 0,0 Z M 15,0 A 15,15 0 0,1 -15,0 A 15,15 0 0,1 0,-15 L 0,-10 A 10,10 0 0,0 -10,0 A 10,10 0 0,0 10,0",

            config: {
                logtransform: false,
                zscore: true,
            },
            rendered: false,
            running: false,
            alert: '',
        };
    },

    props: {
        spreadsheets: Array
    },

    methods: {
        setPCAPointStyles: function() {
            let vm = this;

            let pca_plot = Plotly.d3.select("#pca_plot");
            let points = pca_plot.selectAll(".scatter").selectAll("path");

            // remove any existing background circles
            pca_plot.selectAll(".scatter").selectAll("circle").remove();
            // Add in background circles
            points.each(function(x,i,j) {

                let t = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                t.setAttributeNS(null, "r", "13");
                t.setAttributeNS(null, "transform", this.getAttributeNS(null,"transform"));
                t.setAttributeNS(null, "fill", "white");
                this.parentNode.insertBefore(t, this);
            });

            // Set the shape of the points to be the "colored wedge" shape
            points.attr("d", this.PCA_SYMBOL);
            // Rotate the colored wedge by the time (x-value)
            points.attr("transform", function(x,i,j) {
                let spreadsheet = vm.spreadsheets[j];
                let rotation = (spreadsheet.x_values[i] % spreadsheet.timepoints_per_day) / spreadsheet.timepoints_per_day * 360 - 45;

                let curr_transform = this.getAttribute("transform");
                if (curr_transform.indexOf("rotate") < 0) {
                    return curr_transform + " rotate(" + rotation + ")";
                } else {
                    return curr_transform;
                }
            });

            vm.setPCALegend();
        },

        setPCALegend: function() {
            let vm = this;

            let pca_plot = Plotly.d3.select('#pca_plot');
            let info_layer = pca_plot.select('.infolayer');


            // Remove any existing legend
            info_layer.selectAll('.pca_legend').remove();
            info_layer.selectAll('.pca_legend_bg').remove();

            let times = vm.spreadsheets[0].x_label_values.filter(function(t) { if (t < vm.spreadsheets[0].timepoints_per_day) { return 1; } else { return 0; } });
            let labels = times.map( function(t) {return "Timepoint " + (t + 1);} );

            if (times.length > 6) {
                // If there are too many points to show all in the legend
                // then downsample them to be a more reasonable number
                let n = Math.floor(times.length/6);
                times = times.filter( function (x,i) { return (i % n) === 0; });
                labels = labels.filter( function (x,i) { return (i % n) === 0; });
            }

            let margin = 5;
            let entry_height = 30;
            let radius = 15;
            let legend_width = 200;
            let legend_height = (entry_height+margin)*times.length + margin;
            let x = 800;
            let y = 50;

            // Expand the SVG to fit the legend
            pca_plot.selectAll('.main-svg').attr('width', this.PCA_WIDTH + margin*2 + legend_width);

            // Background rect
            let bg = info_layer.append('rect')
                        .attr('class', 'pca_legend_bg')
                        .attr('x', x + margin)
                        .attr('y', y + margin)
                        .attr('width', legend_width)
                        .attr('height', legend_height)
                        .attr('fill', 'rgb(238,238,238)');

            // Group containing all the entries in the legend, translated to be inside the bg rect
            let g = info_layer.append('g')
                    .attr('class', 'pca_legend')
                    .attr('transform', 'translate(' + (x + 2*margin) + "," + (y + 2*margin) + ")");

            // Each entry is a path (the symbol, appropriately rotated) and text describing the time
            let entries = g.selectAll('g')
                            .data(times)
                           .enter()
                             .append('g')
                             .attr('transform', function (x,i) {return 'translate(0,'+ (i*(entry_height+margin)) + ')';});
            entries.append('path')
                    .attr('transform', function (x,i) {
                            return 'translate(' + radius + ',' + radius + ')'
                                  +'rotate(' + ((times[i] % vm.spreadsheets[0].timepoints_per_day) / vm.spreadsheets[0].timepoints_per_day * 360 - 45) + ')';
                        })
                    .attr('d', this.PCA_SYMBOL)
                    .attr('fill', 'rgb(127,127,127)');

            entries.append('text')
                    .attr('x',2*radius + margin)
                    .attr('transform', 'translate(0,' + radius + ')')
                    .attr('dy', '0.4em')
                    .text(function (x,i) { return labels[i]; });
        },

        runPCA: function() {
            let vm = this;

            // We only run PCA on unfiltered genes below the selected row
            let selected_genes = app.sort_order.filter( function(row,rank) {
                if (rank > app.selected_row) {
                    return false;
                }
                if (app.filtered[row]) {
                    return false;
                }
                return true;
            });

            if (selected_genes.length <  3) {
                vm.alert = "Too few rows selected, need at least 3 for PCA.";
                return;
            } else {
                vm.alert = '';
            }

            let pt_labels = vm.spreadsheets.map( function(spreadsheet, idx) {
                let rep_counts = [];
                return spreadsheet.x_values.map( function(time) {
                    if (rep_counts[time] === undefined) {
                        rep_counts[time] = 0;
                    }
                    rep_counts[time] += 1;
                    let day = Math.floor(time / spreadsheet.timepoints_per_day) + 1;
                    let time_of_day = time % spreadsheet.timepoints_per_day + 1;
                    return "Day " + day + " Timepoint " + time_of_day + " Rep " + rep_counts[time];
                });
            });

            vm.running = true;

            $.ajax({
                url: "/spreadsheets/run_pca",
                data: JSON.stringify({'spreadsheet_ids': app.spreadsheet_ids,
                                      'selected_genes': selected_genes,
                                      'take_logtransform': vm.config.logtransform,
                                      'take_zscore': vm.config.zscore}),
                dataType: 'json',
                contentType: 'application/json',
                type: 'POST',
                success: function (response) {
                    pca_coords = response['pca_coords'];
                    explained_variance = response['explained_variance'];

                    let traces = vm.spreadsheets.map( function (spreadsheet, idx) {
                        return {
                            x: pca_coords[idx][0],
                            y: pca_coords[idx][1],
                            mode: 'markers',
                            name: spreadsheet.descriptive_name,
                            text: pt_labels[idx],
                            marker: {
                                size: 25,
                                opacity: 1,
                            }
                        };
                    });

                    let layout = {
                        height: vm.PCA_HEIGHT,
                        width: vm.PCA_WIDTH,
                        xaxis: {
                            title: "PC1 (" + toFixed(explained_variance[0]*100,1) + "%)"
                        },
                        yaxis: {
                            title: "PC2 (" + toFixed(explained_variance[1]*100,1) + "%)"
                        },
                        hovermode: 'closest',
                        legend: {
                            x:0,
                            y:1,
                            bgcolor: '#EEEEEE'
                        }
                    };

                    let pca_plot = document.getElementById('pca_plot');
                    Plotly.newPlot(pca_plot, traces, layout);

                    pca_plot.on('plotly_afterplot', vm.setPCAPointStyles);
                },
                error: function (error) {
                    console.log("Error running PCA");
                    console.log(error);

                    nitecap_error_message.text("Error running PCA");
                    nitecap_error.modal();
                },
                complete: function() {
                    vm.running = false;
                    vm.rendered = true;
                }
            });
        },

        downloadPCA: function() {
            // NOTE: we cannot use Plotly.downloadImage() since we have modified the plot
            // after its creation and the downloadImage() won't reflect those changes
            // So instead we just directly grab its SVG structure by toSVG() and then download that

            // Gather the plot as an SVG
            let pca_plot = document.getElementById('pca_plot');
            let svg_data = Plotly.Snapshot.toSVG(pca_plot, {format: 'svg'});

            // Create a URL for it
            let blob = new Blob([svg_data]);
            let url = URL.createObjectURL(blob);

            // Trigger downloading of the URL by making an <a href ...> to it and clicking it
            let anchor = document.createElement("a");
            anchor.href = url;
            anchor.download = "pca.svg";
            document.body.appendChild(anchor);
            anchor.click();
            document.body.removeChild(anchor);

            // Cleanup after 60s, they've presumably successfully downloaded the small svg
            setTimeout(function () { URL.revokeObjectURL(url) }, 60000);
        },
    },

    watch: {
        "config": {
            handler: "runPCA",
            deep: true
        },
    },

    template: '\
    <div>\
        <div class="col card">\
            <div class="card-body">\
                <button id="run_pca" class="btn btn-primary"\
                    v-bind:disabled="running"\
                    v-on:click="runPCA">\
                    {{running ? "Processing..." : "Run PCA"}}\
                    <span v-if="running" class=\'spinner-border spinner-border-sm text-light mr-2\' role=\'status\' aria-hidden=\'true\'>\
                    </span>\
                </button>\
                <span class="alert alert-error" v-if="alert !== \'\'">{{alert}}</span>\
\
                <div id="pca_plot"></div>\
\
                <span id="pca_controls" class="col" v-if="rendered">\
                    <span>log(x+1) Transform</span>\
                    <label class="switch">\
                        <input id="pca_logtransform" name="pca_logtransform" type="checkbox" v-model="config.logtransform"/>\
                        <span class="slider"></span>\
                    </label>\
\
                    <span for="pca_zscore">Z-Score Normalization</span>\
                    <label class="switch">\
                        <input id="pca_zscore" name="pca_zscore" type="checkbox" v-model="config.zscore">\
                        <span class="slider"></span>\
                    </label>\
\
                    <button id="download_pca" class="btn btn-primary" v-on:click="downloadPCA">Download PCA</button>\
                </span>\
            </div>\
        </div>\
    </div>\
    ',
});
