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

var formatNum = function(num, digits) {
    if (isNaN(num)) {
        return "N/A";
    } else if (num === null) {
        return "N/A";
    } else if (num === 0.0) {
        return "0";
    }

    let magnitude = Math.abs(num);
    let digits_above_zero = Math.max(Math.floor(Math.log10(magnitude)), 1);

    let large_cutoff = Math.pow(10, digits);
    let small_cutoff = Math.pow(10, -digits+1);
    if (magnitude >= large_cutoff) {
        return num.toExponential(digits-3);
    } else if (magnitude < small_cutoff) {
        return num.toExponential(digits-3);
    } else {
        return num.toFixed(digits - digits_above_zero);
    }
}
var toFixed = function(num, i) {
    // Call num.toFixed unless num is undefined (eg: null)
    if (typeof num === 'number') {
        return num.toFixed(i);
    }
    return num + '';
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
    } else if (isNaN(b) || b === null) {
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

// Util that takes a two-dim array-of-arrays and computes the maximum of each row
function maximums(table) {
    return table.map(array_max);
}

// Util that takes a two-dim array-of-arrays and computes the minimum of each row
function minimums(table) {
    return table.map(array_min);
}

// Util that takes a two-dim array-of-arrays and computes the mean of each row
// If some entries are NaN, they are dropped from the averaging
function means(table) {
    function mean(row) {
        let sum = 0;
        let count = 0;
        row.forEach( function (x) {
            if (isNaN(x) || x === null) {
                return;
            }
            count += 1;
            sum += x;
        });
        return sum / count;
    }

    return table.map(mean);
}

// Util to pad a string with copies of a character
function padEnd(string, length, character) {
    if (string.length > length) {
            return string;
    } else {
        return string + new Array(length - string.length + 1).join(character);
    }
}

// Pad zeros in front of an integer
function zeroPad(integer, num_digits) {
    let s = toString(integer);
    if (s.length > num_digits) {
        return s;
    }
    return new Array(num_digits - s.length + 1).join('0') + s;
}

/// Util functions for finding column labels (timepoint/day counts) from headers
var column_label_formats = [
            // Formats with CT, eg CT04
            {format: new RegExp("CT(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'CT'+zeroPad(x,2);
            }},
            {format: new RegExp("ct(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'ct'+zeroPad(x,2);
            }},
            {format: new RegExp("(\\d+)CT"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'CT';
            }},
            {format: new RegExp("(\\d+)ct"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'ct';
            }},
            // Formats with ZT, eg ZT04
            {format: new RegExp("ZT(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'ZT'+zeroPad(x,2);
            }},
            {format: new RegExp("zt(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'zt'+zeroPad(x,2);
            }},
            {format: new RegExp("(\\d+)ZT"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'ZT';
            }},
            {format: new RegExp("(\\d+)zt"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'zt';
            }},
            // Just numbers, nothing else
            {format: new RegExp("^(\\d+)$"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return ''+x;
            }},
            // 12:34 style label
            {format: new RegExp("(\\d+):(\\d\\d)"),
             make_label: function(x, wrapped) {
                let hours = Math.floor(x/60);
                let minutes = x - hours;
                if (wrapped) { hours = hours % 24; }
                return zeroPad(hours, 2) + ':' + zeroPad(minutes, 2);
             }}
];
var clock_time_regexp = new RegExp("(\\d+):(\\d\\d)");

function inferColumnTimes(columns, days, timepoints) {
    let best_num_matches = 0;
    let best_matches = [];
    let best_format = null;

    column_label_formats.forEach( function(fmt) {
        let matches = columns.map( function(label) { return fmt.format.exec(label); } );
        let num_matches = matches.filter( function(match) { return match !== null; }).length;
        if (num_matches > best_num_matches) {
            best_num_matches = num_matches;
            best_matches = matches;
            best_format = fmt;
        }
    });

    if (best_num_matches === 0) {
        return null;
    }

    // Try to convert the match to numbers, first as just plain integers than as ##:## clock times into minutes since midnight
    let times = best_matches.map( function(match) {
        if (match !== null) {
            if (match.length > 2) {
                let hours = parseInt(match[1]);
                let minutes = parseInt(match[2]);
                return hours*60+minutes;
            } else {
                let val = parseInt(match[1], 10);
                return val;
            }
        } else {
            return null;
        }
    } );

    return {times: times,
            format: best_format,
            matches: best_matches,
            num_matches: best_num_matches};
}

function guessColumnLabels(columns, days, timepoints) {
    let inferred = inferColumnTimes(columns, days, timepoints);

    if (inferred  === null) {
        // Nothing matches any known header format
        return columns.map( function(x) {return "Ignore";} );
    }

    let times = inferred.times;
    let num_matches = inferred.num_matches;

    let min_time = Math.min.apply(null, times.filter(function(t) {return t !== null;}));
    let max_time = Math.max.apply(null, times.filter(function(t) {return t !== null;}));
    let total_time_delta = max_time - min_time;
    let time_per_timepoint = total_time_delta / (timepoints * days - 1);

    let time_point_counts = times.map(function(time,i) {
        if (time !== null) {
            return (time - min_time) / time_per_timepoint;
        } else {
            return null;
        }
    });

    if (time_point_counts.every(function(t) {if (t !== null) {return Number.isInteger(t)} return true;})) {
        let selections = time_point_counts.map( function(time_point_count, i) {
            if (time_point_count === null) {
                if (i == 0) {
                    return "ID";
                } else {
                    return "Ignore";
                }
            }
            return "Day" + (Math.floor(time_point_count / timepoints) + 1) + " Timepoint" + (time_point_count % timepoints + 1);
        });

        return selections;
    }

    // Okay, so the timepoints aren't evenly distributed
    // But let's check there might be the right number of them
    // assuming that there are constant number of reps per day
    // and that they are in the right order
    if (num_matches % (timepoints*days) === 0) {
        let num_reps = Math.floor(num_matches / timepoints*days);

        let selections = [];
        let selected_below = 0;
        columns.map( function(column, i) {
            if (times[i] !== null) {
                day = Math.floor(selected_below / timepoints);
                time = selected_below % timepoints;
                selections[i] = "Day" + (day+1) + " Timepoint" + (time+1);
                selected_below += 1;
            } else {
                if (i == 0) {
                    selections[i] = "ID";
                } else {
                    selections[i] = "Ignore";
                }
            }
        });
        return selections;
    }

    // No selections, we have uneven timepoints
    return columns.map( function(x) {return "Ignore";} );
}

function getLabelOptions(days, timepoints) {
    let options = ["Ignore", "ID"];
    for(let i = 0; i < days; i++) {
        for(let j = 0; j < timepoints; j++) {
            options.push("Day" + (i+1) + " Timepoint" + (j+1));
        }
    }
    return options;
};


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
                    rowSelector.options[i].classList.add("row-disabled");
                } else {
                    rowSelector.options[i].classList.remove("row-disabled");
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
    }, {passive: false}); // indicate that we will prevent default, true may later become the default

    // add the options to the row_selector list
    for(var i = 0; i < num_row_selections; i++) {
        var row_option = document.createElement("div");
        row_option.className = "list-group-item list-group-item-action py-0";
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
