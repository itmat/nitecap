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
    var el = $('[data-toggle="popover"]');
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

//// COMPUTATIONAL UTILS ////
function computeZScores(ordering) {
    return function(data) {
        var zscore = ordering.map( function (i) {
            var row = data[i];
            var num_reps = 0;
            var sum = row.reduce( function(x,y) {
                 if (isNaN(y)) {return x;}
                num_reps += 1;
                return x+y;
            }, 0);

            var mean = sum / num_reps;
            if (num_reps === 0) { mean = 0; }

            var variance = row.reduce( function(x,y) {
                if (isNaN(y)) {return x;}

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

            if (isNaN(value)) {
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

