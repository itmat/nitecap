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
    $('body').popover({
        selector: '[data-toggle="popover"]',
        placement: 'top',
        trigger: 'hover',
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
            // so sort by their indexes instead
            return i - j;
        } else {
            return 1;
        }
    } else if (isNaN(b) || b === null) {
        return -1;
    } else {
        if (a === b) {
            // If both are the same, then preserve their order
            // and sort by their indexes instead (forces stable sorting)
            return i -j;
        } else {
            return a - b;
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
    var sems = stds.map(function (std, time) { return std / Math.sqrt(reps_per_timepoint[time]); });

    return {means: means, variances: variances, stds: stds,  sems:sems};
}

function numNaNTimepoints(data, times) {
    let num_nan = data.map( function(row) {
        let all_nans = [];
        times.map(function (time, i) {
            if (all_nans[time] == undefined) {
                all_nans[time] = true;
            }

            let value = row[i];
            if (!(isNaN(value) || value === null)) {
                all_nans[time] = false;
            }
        });
        return all_nans;
    });
    return sums(num_nan);
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
// NOTE: does not skip NaNs
//If axis=1, then max on each row in the table, i.e. does max(table[i][j]) iterating over j
//If axis=0, then max on each row in the table, i.e. does max(table[i][j]) iterating over i
function maximums(table, axis) {
    axis = axis !== undefined ? axis : 1;

    if (axis === 1) {
        return table.map(array_max);
    } else if (axis === 0) {
        // Select out data[*][j] and take the max
        return table[0].map( function (_,j) {
            return array_max(table.map( function(row) {
                return row[j];
            }));
        });
    } else {
        return "axis must be 0 or 1";
    }
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

// Util that takes a two-dim array-of-arrays and computes the sum of each row
// NaNs are skipped (if all are NaN, then NaN is returned)
// If axis=1,  then sums on each row in the table, ie does sum(table[i][j])  summing over j
// If axis=0, then sums on the first axis, i.e. does sum(table[i][j]) summing over i
function sums(table, axis) {
    axis = axis !== undefined ? axis : 1;

    function sum(row) {
        let sum = 0;
        let count = 0;
        row.forEach( function(x) {
            if (isNaN(x) || x === null) {
                return;
            }
            sum += x;
            count += 1;
        } );

        if (count === 0) {
            return NaN;
        }
        return sum;
    };

    if (axis === 1) {
        // Take the sum of data[i][*]
        return table.map(sum);
    } else if (axis === 0) {
        // Select out data[*][j] and take the sum
        return table[0].map( function (_,j) {
            return sum(table.map( function(row) {
                return row[j];
            }));
        });
    } else {
        return "axis must be 1 (default) or 0";
    }
}

// Util that takes a two-dim array-of-arrays and computes the number of non-NaN elements
// in each row
function numValids(table) {
    function count(row) {
        let count = 0;
        row.forEach( function(x) {
            if( isNaN(x) || x === null ){
                return;
            }
            count += 1;
        });
        return count;
    }
    return table.map(count);
}

// Util to compute the ranks of an array, i.e. order in which they will be sorted
// 'array' is the numerical array to rank
// 'direction' is +/- 1, positive if sorting ascending (rank 0 = smallest), negative if descendin
function rankArray(array, direction) {
    direction = direction !== undefined ? direction : 1;

    let sort_order =  array.map( function(x,i) {return i;} );
    sort_order = sort_order.sort(function(i,j) {
        return direction*(array[i] - array[j]);
    });

    let ranks = new Array(array.lengths);
    sort_order.forEach(function(i,j) {
        ranks[i] = j;
    });
    return ranks;
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
            // Formats with HR, eg 00hr
            {format: new RegExp("HR(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'HR'+zeroPad(x,2);
            }},
            {format: new RegExp("hr(\\d+)"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return 'hr'+zeroPad(x,2);
            }},
            {format: new RegExp("(\\d+)HR"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'HR';
            }},
            {format: new RegExp("(\\d+)hr"),
             make_label: function(x, wrapped) {
                if (wrapped) {x = x % 24;}
                return zeroPad(x,2)+'hr';
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
                let minutes = x - 60*hours;
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

function guessColumnLabels(columns, days, timepoints, defaults) {
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
    return defaults;
}

function getLabelOptions(days, timepoints) {
    let options = ["Ignore", "ID", "Stat"];
    for(let i = 0; i < days; i++) {
        for(let j = 0; j < timepoints; j++) {
            options.push("Day" + (i+1) + " Timepoint" + (j+1));
        }
    }
    return options;
};

// Polyfill for Object.entries for IE support
// From MDN https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Object/entries
if (!Object.entries) {
  Object.entries = function( obj ){
    var ownProps = Object.keys( obj ),
        i = ownProps.length,
        resArray = new Array(i); // preallocate the Array
    while (i--)
      resArray[i] = [ownProps[i], obj[ownProps[i]]];

    return resArray;
  };
}
