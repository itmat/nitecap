$(document).ready(function () {

    // Needed to make popovers work
    $("[data-toggle=popover]").popover();

    setCopyrightYear();
});


// Sets copyright year
function setCopyrightYear() {
    $('#copyrightYear').html(new Date().getFullYear());
}