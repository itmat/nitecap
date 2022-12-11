import argparse
parser = argparse.ArgumentParser(description="Transform an GO-basic .obo file from GO into a .txt file mapping ontologies to their parents (from http://purl.obolibrary.org/obo/go/go-basic.obo)")
parser.add_argument("obo_file", help="Path to the .obo file to read")
parser.add_argument("out_file", help="Path to write out the tab-separated table mapping GO terms to their parents")
parser.add_argument("definition_file", help="Path to write out the definition table, mapping GO ID's to names")

args = parser.parse_args()

import pandas

with open(args.obo_file) as obo_file:
    is_as = []
    relationships = []
    definitions = {}
    current_id = None
    for line in obo_file:
        if line.startswith("id:"):
            current_id = line.split()[1]
        elif line.startswith("is_a:"):
            is_as.append((current_id, line.split()[1]))
        elif line.startswith("relationship:"):
            _, rel_type, target = line.split()[:3]
            relationships.append((current_id, target, rel_type))
        elif line.startswith('name:'):
            start, rest = line.split(maxsplit=1)
            definitions[current_id] = {"name": rest.strip()}

# Map each term to all of its parents
# We use both "is_a" and other relationships ("part_of" and "regulates")
all_edges = is_as + [(a,b) for (a,b,c) in relationships]
all_nodes = set(a for a,b in all_edges).union(b for a,b in all_edges)
# Start with parent-less nodes
working_nodes = [node for node in all_nodes
                    if not any(a == node for a,b in all_edges)]
parents = {node:set() for node in working_nodes}
while len(working_nodes) > 0:
    edges_into = [(a,b) for (a,b) in all_edges if b in working_nodes]
    for a,b in edges_into:
        parents[a] = parents.get(a, set()) | parents[b] | set([b])
    working_nodes = set(a for a,b in edges_into)

# Output the parent-children relationships to the obo file
rels = []
for node, nodes_parents in parents.items():
    for parent in nodes_parents:
        rels.append({"child": node, "parent": parent})
rels = pandas.DataFrame(rels)

rels.to_csv(args.out_file, sep="\t", index=None)

defs = pandas.DataFrame.from_dict(definitions, orient="index")
defs.index.name = "go_id"
defs.to_csv(args.definition_file, sep="\t")
