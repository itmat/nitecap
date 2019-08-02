let factorials = [1, 1];
function factorial(k) {
    // Memoized factorial function for small k
    if (k <= 1) { return 1; }
    if (factorials[k] !== undefined)  { return factorials[k]; }

    factorials[k] = factorial(k-1) * k;
    return factorials[k];
}

let log_factorials = {};
function log_factorial(k) {
    if (k <= 1) { return 1; }
    if (k < 100) {
        if (log_factorials[k] === undefined) { log_factorials[k] = log_factorial(k-1) + Math.log(k); }
        return log_factorials[k];
    }
    if (log_factorials[k] === undefined) {
        // Stirlings approximation for large k
        log_factorials[k] = k * Math.log(k) - k + Math.log(2 * Math.PI * k) / 2;
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
    for (let k = intersection_size; k <= sample_size; k++) {
        p += hypergeometric_prob(background_size, set_size, sample_size, k);
    }
    return p;
}

function test_pathway(selected_set, pathway, background_list) {
    let intersection_size = 0;
    selected_set.forEach(function(id) {
        if (pathway.indexOf(id.toUpperCase()) >= 0) {
            intersection_size += 1;
        }
    });
    return hypergeometric_test(background_list.length,
                    pathway.length,
                    selected_set.length,
                    intersection_size);
}

function test_pathways(selected_set, background_list, pathways) {
    // Compute p values of each pathway
    let ps = pathways.map( function (pathway) {
        return {name: pathway.name, url: pathway.url, p: test_pathway(selected_set, pathway.ids, background_list)};
    });
    return ps;
}

function restrict_pathways(pathways, background_list) {
    background_list = background_list.map( function( id) { return id.toUpperCase(); });
    // Restrict pathways to those ids that appear in our background list
    return pathways.map( function(pathway) {
        return {name: pathway.name,
                url: pathway.url,
                ids: pathway.ids.filter( function(id) {
                        return background_list.indexOf(id) >= 0;
                    })
                };
    });
}
