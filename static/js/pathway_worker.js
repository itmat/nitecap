importScripts("/static/js/pathway.js");

let pathways = [];

onmessage = function(message) {
    if (message.data.type == "set_pathways") {
        pathways = message.data.pathways;
    } else if(message.data.type == "run_analysis") {
        let tests =  test_pathways(message.data.foreground, message.data.background, pathways);
        let results = tests['results'].sort( function(p1, p2) {
            return p1.p - p2.p;
        });
        // Freeze it so that it's non-reactive.
        // Adding reactivity is too slow
        Object.freeze(results);

        postMessage({
            results: results,
        });
    } else {
        console.log("ERROR: unexpected message in pathway worker:", message.data);
    }
};
