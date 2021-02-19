let factorials = [1, 1];
function factorial(k) {
    // Memoized factorial function for small k
    if (k <= 1) { return 1; }
    if (factorials[k] !== undefined)  { return factorials[k]; }

    factorials[k] = factorial(k-1) * k;
    return factorials[k];
}

let log_factorials = [0,0];
function log_factorial(k) {
    if (k <= 1) { return 0; }
    if (log_factorials[k] === undefined) {
        for(let i = log_factorials.length; i <= k; i++) {
            log_factorials[i] = log_factorials[i-1] + Math.log(i);
        }
    }
    return log_factorials[k];
}

function log_choose(n,k) {
    // log (n choose k)
    return log_factorial(n) - log_factorial(n-k) - log_factorial(k);
}

function hypergeometric_prob(background_size, set_size, sample_size, intersection_size) {
    // Probability mass function for hypergeometric probability distribution
    let log_p = log_choose(set_size,  intersection_size) + log_choose(background_size - set_size, sample_size - intersection_size) - log_choose(background_size, sample_size);
    return Math.exp(log_p);
}

function hypergeometric_test(background_size, set_size, sample_size, intersection_size) {
    // Probability of getting at least `intersection_size` under random sampling
    let p = 0;
    let max_intersection = Math.min(set_size, sample_size);
    for (let k = intersection_size; k <= max_intersection; k++) {
        p += hypergeometric_prob(background_size, set_size, sample_size, k);
    }
    return p;
}

function test_pathway(selected_set, pathway, background_list) {
    // Compute size of overlap of pathway and the selected set
    let intersection_size = 0;
    if (selected_set.size < pathway.size) {
        // Pick whether selected_set or pathway should be used as the reference
        // to compare to. Faster to iterate over the smaller one
        selected_set.forEach(function(id) {
            if (pathway.has(id)) {
                intersection_size += 1;
            }
        });
    } else {
        pathway.forEach(function(id) {
            if (selected_set.has(id)) {
                intersection_size += 1;
            }
        });
    }

    let p = hypergeometric_test(background_list.size,
                    pathway.size,
                    selected_set.size,
                    intersection_size);
    return {p: p, overlap: intersection_size};
}

function test_pathways(selected_set, background_list, pathways) {
    // Capitalize background
    background_list = new Set(background_list.map(function(id) {return id.toUpperCase();}));

    // Capitalize and intersect with background
    selected_set = new Set(selected_set.filter(function(id) { return background_list.has(id); }).map(function(id) {return id.toUpperCase();}));

    // Compute p values of each pathway
    let ps = pathways.map( function (pathway) {
        let result = test_pathway(selected_set, pathway.feature_ids, background_list);
        Object.assign(result, pathway);
        Object.assign(result, {
            background_size: background_list.size,
            selected_set_size: selected_set.size,
            pathway_size: pathway.feature_ids.size,
        });
        return result;
    });
    return {"results": ps, "background": background_list, "foreground": selected_set};
}

function restrict_pathways(pathways, background_list) {
    background_list = new Set(background_list.map( function( id) { return id.toUpperCase(); }));
    // Restrict pathways to those ids that appear in our background list
    return pathways.map( function(pathway) {
        let p = Object.assign({}, pathway);
        Object.assign(p, {
            feature_ids: new Set(pathway.feature_ids.filter( function(id) {
                return background_list.has(id);
            })),
        });
        return p;
    });
}
