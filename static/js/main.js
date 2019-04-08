$(document).ready(function () {
    setCopyrightYear();
});


// Sets copyright year
function setCopyrightYear() {
    $('#copyrightYear').html(new Date().getFullYear());
}