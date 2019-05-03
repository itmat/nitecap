$(document).ready(function () {

    // Needed to make popovers work
    initializePopovers();

    setCopyrightYear();
});


// Sets copyright year
function setCopyrightYear() {
    $('#copyrightYear').html(new Date().getFullYear());
}

// Initialize popovers
function initializePopovers() {
    var el = $('.help-pointer[data-toggle="popover"]');
    el.on('click', function(e){
        var el = $(this);
        setTimeout(function(){
            el.popover('show');
        }, 200); // Must occur after document click event below.
    })
    .on('shown.bs.popover', function(){
        $(document).on('click.popover', function() {
            el.popover('hide'); // Hides all
        });
    })
    .on('hide.bs.popover', function(){
        $(document).off('click.popover');
    });
}

var toFixed = function(num, i) {
    // Call num.toFixed unless num is undefined (eg: null)
    if (typeof num === 'number') {
        return num.toFixed(i);
    }
    return num;
};
var toString = function(num) {
    // Call num.toString unless num is undefined (eg: null)
    if (typeof num === 'number') {
        return num.toString();
    }
    return num + '';
};

// For sorting values with nans, returns -1,0,1 based off value and current index
function compare(a,b, i,j) {
    // Handle nans, putting them at the end
    if (isNaN(a) || a === null) {
        if (isNaN(b) || b === null) {
            // If both are Nans, then we preserve their order
            if (i > j) {
                return 1;
            } else if (i < j) {
                return -1;
            } else {
                return 0;
            }
        } else {
            return 1;
        }
    } else if (isNaN(b)) {
        return -1;
    } else {
        if (a > b) {
            return 1;
        } else if (a < b) {
            return -1;
        } else {
            return 0;
        }
    }
}

//// COMPUTATIONAL UTILS ////
function computeZScores(ordering) {
    return function(data) {
        var zscore = ordering.map( function (i) {
            var row = data[i];
            var num_reps = 0;
            var sum = row.reduce( function(x,y) {
                 if (isNaN(y) || y === null) {return x;}
                num_reps += 1;
                return x+y;
            }, 0);

            var mean = sum / num_reps;
            if (num_reps === 0) { mean = 0; }

            var variance = row.reduce( function(x,y) {
                if (isNaN(y) || y === null) {return x;}

                return x + (y - mean)*(y - mean);
            }, 0);
            var std = Math.sqrt(variance);

            var z_scores = row.map( function(x,i) {
                return (x - mean) / std;
            } );

            return z_scores;
        } );
        return zscore;
    };
}

function meanByTimepoints(data, times) {
    var means = data.map( function(row) {
        var sum_by_timepoint = [];
        var reps_by_timepoint = [];
        times.map( function (time,i) {
            var value = row[i];

            if (sum_by_timepoint[time] === undefined) {
                sum_by_timepoint[time] = 0;
                reps_by_timepoint[time] = 0;
            }

            if (isNaN(value) || value === null) {
                return;
            }

            sum_by_timepoint[time] += value;
            reps_by_timepoint[time] += 1;
        });
        var mean_by_timepoint = sum_by_timepoint.map( function(sum,i) {
            if (reps_by_timepoint[i] === 0) {return 0;}
            return sum / reps_by_timepoint[i];
        });
        return mean_by_timepoint;
    });

    return means;
}

function rowStatsByTimepoint(row, times) {
    var sum_by_timepoint = [];
    var reps_per_timepoint = [];
    times.forEach(function (time, i) {
        var value = row[i];

        if (sum_by_timepoint[time] === undefined) {
            sum_by_timepoint[time] = 0;
            reps_per_timepoint[time] = 0;
        }
        if (!isNaN(value) && value !== null) {
            // Skip nans entirely, count the rest
            sum_by_timepoint[time] += value;
            reps_per_timepoint[time] += 1;
        }
    });

    var means = sum_by_timepoint.map( function (sum,i) {
        return sum / reps_per_timepoint[i];
    } );

    var variances = [];
    times.forEach( function(time, i) {
        var value = row[i];

        if (variances[time] === undefined) {
            variances[time] = 0;
        }

        if (!isNaN(value) && value !== null) {
            if (reps_per_timepoint[time] > 1) {
                variances[time] += (value - means[time])*(value - means[time]) / (reps_per_timepoint[time]-1);
            } else {
                variances[time] = 0;
            }
        }
    });

    var stds = variances.map(Math.sqrt);
    var sems = stds.map(function (std, time) { return std / reps_per_timepoint[time]; });

    return {means: means, variances: variances, stds: stds,  sems:sems};
}

// Util to compute maximum of an array along its axis
// Apparently Math.max.apply can fail for large arrays
var array_max = function (array) {
    return array.reduce( function(a,b) {
        return Math.max(a,b);
    } );
};
var array_min = function (array) {
    return array.reduce( function(a,b) {
        return Math.min(a,b);
    } );
};

// Util to pad a string with copies of a character
function padEnd(string, length, character) {
    if (string.length > length) {
            return string;
    } else {
        return string + new Array(length - string.length + 1).join(character);
    }
}

//// Row selector object ////
function makeRowSelector(element, labels, q_values, filtered, sort_order, num_row_selections, onSelect) {
    let rowSelector = {
        top: 0, // Top row visible
        options: [], // List of all the option elements inside of the row selector
        labels: labels, // list of strings used to label the rows
        full_labels: labels, // the labels not shortened (incase they exceed the maximum length) for hovertext
        sort_order: sort_order, // List of indexes to use to reorder the rows
        filtered_rows: filtered, // Boolean list with 1 meaning corresponding row is filtered out (disabled)
        label_length_maximum: 30, // longest label to ever make

        // Event callbacks
        onSelect: onSelect,

        // Methods
        makeRowLabels: function(labels, q_values) {
            // Make labels that include q values in them, for the selector
            let max_label_length = Math.max.apply(0, labels.map( function (x) {return x.length;}));
            max_label_length = Math.min(max_label_length, rowSelector.label_length_maximum);

            rowSelector.labels = labels.map( function(label, i) {
                label = String(label).slice(0,rowSelector.label_length_maximum);
                return padEnd(label, max_label_length, ' ') + ' Q: ' + toFixed(q_values[i], 2);
            } );

            rowSelector.full_labels = labels;
            rowSelector.update();
        },

        filterRows: function(filtered_rows) {
            rowSelector.filtered_rows = filtered_rows;
            rowSelector.disableFilteredRows();
        },

        disableFilteredRows: function() {
            for(var i = 0; i < num_row_selections; i++) {
                var current_index = rowSelector.sort_order[rowSelector.top + i];
                if (rowSelector.filtered_rows[current_index]) {
                    rowSelector.options[i].classList.add("disabled");
                } else {
                    rowSelector.options[i].classList.remove("disabled");
                }
            }
        },

        setSortOrder: function(sort_order) {
            rowSelector.sort_order = sort_order;
            rowSelector.update();
        },

        update: function () {
            // Update the selector rows
            for(var i = 0; i < num_row_selections; i++) {
                var current_index = rowSelector.top + i;
                if (current_index < 0) {
                    rowSelector.options[i].textContent = "-";
                    rowSelector.options[i].title = "-";
                } else if (current_index >= rowSelector.labels.length) {
                    rowSelector.options[i].textContent = "-";
                    rowSelector.options[i].title = "-";
                } else {
                    rowSelector.options[i].textContent = rowSelector.labels[rowSelector.sort_order[current_index]];
                    rowSelector.options[i].title = rowSelector.full_labels[rowSelector.sort_order[current_index]];
                }

                if (current_index === rowSelector.selectedRow) {
                    rowSelector.options[i].classList.add("active");
                } else {
                    rowSelector.options[i].classList.remove("active");
                }
            }

            // Visually disable filtered options
            rowSelector.disableFilteredRows();
        },

        selectRow: function (row_index) {
            rowSelector.selectedRow = row_index;

            // Update row selector scrolling
            if (row_index >= rowSelector.top) {
                if (row_index < rowSelector.top + num_row_selections) {
                    // Do nothing, already can see the right row
                } else {
                    // Moving down, put it at the bottom
                    rowSelector.top = row_index - num_row_selections + 1;
                }
            } else {
                // Moving up, put it at the top
                rowSelector.top = row_index;
            }

            rowSelector.update();

            rowSelector.onSelect(rowSelector.selectedRow);
        }
    };

    element.addEventListener('keydown', function (event) {
        if (event.defaultPrevented) {
            return; // Do nothing
        }

        switch (event.key) {
            case "Down": // IE/Edge specific value
            case "ArrowDown":
                // Find the next row down that is unfiltered
                var i = rowSelector.selectedRow+1;
                while (true) {
                    if (i >= rowSelector.labels.length) {
                        // End of the table, do nothing;
                        break;
                    }
                    if (!rowSelector.filtered_rows[rowSelector.sort_order[i]]) {
                        rowSelector.selectRow(i);
                        break;
                    }
                    i++;
                }
                break;
            case "Up": // IE/Edge specific value
            case "ArrowUp":
                // Find the next row up that is unfiltered
                var i = rowSelector.selectedRow-1;
                while (true) {
                    if (i < 0) {
                        // Top of the table, do nothing;
                        break;
                    }
                    if (!rowSelector.filtered_rows[rowSelector.sort_order[i]]) {
                        rowSelector.selectRow(i);
                        break;
                    }
                    i--;
                }
                break;
            case "PageDown":
                var max_top = Math.max(0, rowSelector.labels.length - num_row_selections);
                rowSelector.top = Math.min(rowSelector.top + num_row_selections, max_top);
                rowSelector.update();
                break;
            case "PageUp":
                rowSelector.top = Math.max(rowSelector.top - num_row_selections, 0);
                rowSelector.update();
                break;
            default:
                return;
        }

        event.preventDefault();
        return;
    });

    element.addEventListener('wheel', function (event) {
        if (event.deltaY > 0) {
            var max_top = Math.max(0, rowSelector.labels.length - num_row_selections);
            rowSelector.top = Math.min(rowSelector.top + 3, max_top) ;
        } else if (event.deltaY < 0) {
            rowSelector.top = Math.max(rowSelector.top - 3, 0) ;
        }
        rowSelector.update();

        event.preventDefault();
    });

    // add the options to the row_selector list
    for(var i = 0; i < num_row_selections; i++) {
        var row_option = document.createElement("div");
        if (i === num_row_selections) {
            row_option.className = "list-group-item list-group-item-action py-0";
        } else {
            row_option.className = "list-group-item list-group-item-action py-0";
        }
        row_option.textContent = "Loading...";

        let my_index = i;
        row_option.addEventListener('click', function (event) {
            let row = rowSelector.top + my_index;
            rowSelector.selectRow(row);
        } );
        rowSelector.options.push(row_option);

        element.appendChild(row_option);
    }

    rowSelector.makeRowLabels(labels, q_values);

    return rowSelector;
}
