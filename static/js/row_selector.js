Vue.component('row-selector', {
    data: function () {
        return {
            top: 0,
        };
    },

    props: {
        selectedRow: Number,
        numRows: Number,
        sortOrder: Array,
        filtered: Array,
        selectRow: Function,
        labels: Array,
        labelMaxLength: Number,
        qValues: Array,
    },

    methods: {
        goDown: function (event) {
            // Find the next row down that is unfiltered
            var i = this.selectedRow+1;
            while (true) {
                if (i >= this.labels.length) {
                    // End of the table, do nothing;
                    break;
                }
                if (!this.filtered[this.sortOrder[i]]) {
                    this.selectRow(i);
                    break;
                }
                i++;
            }
        },

        goUp: function () {
            // Find the next row up that is unfiltered
            var i = this.selectedRow-1;
            while (true) {
                if (i < 0) {
                    // Top of the table, do nothing;
                    break;
                }
                if (!this.filtered[this.sortOrder[i]]) {
                    this.selectRow(i);
                    break;
                }
                i--;
            }
        },

        pageDown: function () {
            var max_top = Math.max(0, this.labels.length - this.numRows);
            this.top = Math.min(this.top + this.numRows, max_top);
        },

        pageUp: function () {
            this.top = Math.max(this.top - this.numRows, 0);
        },
    },

    computed: {
        rows: function () {
            let vm = this;
            let rows_ = [];
            let base_class = "list-group-item list-group-item-action py-0"
           for(let i = 0; i < vm.numRows; i++) {
                let idx = vm.sortOrder[i + vm.top];
                if (idx > vm.fullLabels.length) {
                    return {label: '-', rawLabel: '-', filtered: true, selected: false, index: idx, class:base_class};
                }

                let selected = vm.selectedRow == (i + vm.top);
                let filtered = vm.filtered[idx];
                rows_[i] = {
                    label: vm.fullLabels[idx],
                    rawLabel: vm.labels[idx],
                    filtered: filtered,
                    selected: selected,
                    index: i + vm.top,
                    class: base_class + (selected ? ' active' : '') + (filtered ? ' row-disabled' : ''),
                };
            }
            return rows_;
        },

        fullLabels: function () {
            let vm = this;
            let desired_label_length = Math.max.apply(0, vm.labels.map( function (x) {return x.length;}));
            desired_label_length = Math.min(desired_label_length, vm.labelMaxLength);

            return vm.labels.map( function(label, i) {
                label = String(label).slice(0,vm.labelMaxLength);
                label = padEnd(label, desired_label_length, ' ');

                if (vm.qValues !== null) {
                    let q = vm.qValues[i];
                    return label + ' Q: ' + toFixed(vm.qValues[i], 2);
                } else {
                    return label;
                }
            });
        },
    },

    watch: {
        "selectedRow": function () {
            let row_index = this.selectedRow;
            // Update row selector scrolling
            if (row_index >= this.top) {
                if (row_index < this.top + this.numRows) {
                    // Do nothing, already can see the right row
                } else {
                    // Moving down, put it at the bottom
                    this.top = row_index - this.numRows + 1;
                }
            } else {
                // Moving up, put it at the top
                this.top = row_index;
            }
        },
    },

    mounted: function () {
        let vm = this;
        vm.$el.addEventListener('wheel', function (event) {
            if (event.deltaY > 0) {
                var max_top = Math.max(0, vm.labels.length - vm.numRows);
                vm.top = Math.min(vm.top + 3, max_top) ;
            } else if (event.deltaY < 0) {
                vm.top = Math.max(vm.top - 3, 0) ;
            }

            event.preventDefault();
        }, {passive: false}); // indicate that we will prevent default, true may later become the default
    },

    template: "\
    <div> \
        <h5>Spreadsheet Rows</h5> \
        <div class='list-group row-selector' tabindex='0'\
                   v-on:keydown.down.prevent='goDown' v-on:keydown.up.prevent='goUp' \
                   v-on:keydown.page-up.prevent='pageUp' v-on:keydown.page-down.prevent='pageDown'> \
           <div v-for='row in rows'\
                v-bind:disabled='row.filtered' \
                v-bind:class='row.class'\
                v-on:click='selectRow(row.index)' \
                v-bind:key='row.index'\
                v-bind:title='row.rawLabel'\
                >{{row.label}}</div> \
        </div>\
    </div>",
});
