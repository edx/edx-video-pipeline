// Eventing and Form Handling
// Upload Page

var information_fields = {
    "course_name" : "Institution and Course Name",
    "course_url" : "edX Studio URL"
};

var field_information = {
    "course_url" : 75,
    "course_name" : 60
};

var field_value = {
    "course_url" : "https://studio.edx.org/course/"
};

var field_validation = {
    "course_url" : "is_url",
    "pm_email" : "is_email",
};

// ADD FILENAME //
function add_filename(filename) {
    $.ajax({
        url : "../about_input/", // the endpoint
        type : "POST", // http method
        data : {
            abvid_serial : window.abvid_serial,
            orig_filename : filename
        }, 

        success : function(json) {
            console.log('filename input // sanity check');
        },
        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }

    });
}

function begin_transcode(success) {
    $.ajax({
        url : "../about_input/", // the endpoint
        type : "POST", // http method
        data : {
            abvid_serial : window.abvid_serial,
            success : success
        }, 

        success : function(json) {
            console.log('transcode input // sanity check');
        },
        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }
    });

    if (success == true) {
        $('#uploadselect').fadeOut();
        $('#inst_lookup').fadeIn();
        $('#inst_lookup').focus();
    }
}


///////////////////////
// DROPZONE EVENTING //
var success;

window.Dropzone.options.dmz = {
  init: function() {
    this.on("addedfile", function(file) { add_filename(file.name) });
    this.on("success", function(file) { begin_transcode(success=true) });
    this.on("canceled", function(file) { begin_transcode(success=false) });
    this.on("error", function(file) { begin_transcode(success=false) });
  }
};


////////////////
// RESET FORM //
$('#reset-form').hide();
// Reset Button
$('#reset-form').on('reset', function(event){
    event.preventDefault();
    document.location.reload()
});


/////////////
// WARNING //
function create_warning(message) {
    var $warning_div = $("<div>", {
        class: "ul_warning"
    });
    $warning_div.append('<span>'+message+'</span><br>');
    return $warning_div
}


/////////////////
// SUBMIT FORM //
/////////////////
$('#submit-form').hide();
$('#submit-form').on('submit', function(event){
    event.preventDefault();
    console.log("final submit // sanity check");
    var submit = check_submit();
    if (submit == true) {
        submit_data();

        $('#video_info').fadeOut();
        $('#uploadselect').fadeIn();
        $('#dmz').focus();
        $('#submit-form').fadeOut();
    }
});


// Checking Functions //
var is = {
    is_url: function(field) {
        valid = false;
        if (field.indexOf('https://studio.edx.org/course/') > -1 && field.length > 35 ) {
            valid = true
        }
        else {
            valid = "Invalid URL"
        }
        return valid    
    },
    is_email: function(field) {
        if (field.indexOf('@edx.org') > -1) {
            valid = true
        }
        else {
            valid = "Invalid email"
        }
        return valid    
    }
};

function make_textboxes(title, placeholder) {
    var $edit_div = $("<div>", {
        class: "about_vidinf"
        });
    var textbox = document.createElement("input");
    textbox.setAttribute("type", "text");
    textbox.setAttribute("name", title);
    textbox.setAttribute("id", title);
    textbox.setAttribute("style", "float: none !important; margin-left: auto;margin-right: auto;")
    textbox.setAttribute("size", field_information[title]);
    textbox.setAttribute("placeholder", placeholder)
    // textbox.setAttribute("label", placeholder)
    var box_label = document.createElement("label");
    box_label.setAttribute("class", "sr");
    box_label.setAttribute("for", title);
    box_label.setAttribute("value", placeholder);
    $edit_div.append(box_label)

    if (field_value[title] != undefined ) {
        textbox.setAttribute("value", field_value[title])
        textbox.setAttribute("aria-describedby", "Full URL path to edX studio course instance")
        // Needed?
        var $html_span = '<span class=\"field_title\">edX Studio Course URL</span>'
        $edit_div.append($html_span)

    }
    $edit_div.append(textbox);
    $('#vid_inf').append($edit_div);
}


// Generate Information
var i;
for (i in information_fields) {
    make_textboxes(title=i, placeholder=information_fields[i])
}

function check_submit() {

    var submits = [];

    for (j in information_fields) {
        if (field_validation[j] != undefined) {
            console.log(field_validation[j]);
            // Variable function names
            is[field_validation[j]](field=$('#'+j).val());
            if (valid != true) {
                $('#'+j).parent().find('.ul_warning').empty();
                var $add = create_warning(message=valid);
                $('#'+j).parent().prepend($add);
                $('#'+j).attr("style", "float: none !important; margin-left: auto;margin-right: auto; border-color: #FF0000;");
                submits.push(false);
            }
            else {
                $('#'+j).parent().find('.ul_warning').empty();
                $('#'+j).attr("style", "float: none !important; margin-left: auto;margin-right: auto; border-color: #00A731;");
                submits.push(true)
            }
        }
    }
    submit = true;
    if (submits.indexOf(false) > -1) {
        submit = false
    }
    return submit
}


function submit_data() {
    $.ajax({
        url : "../about_input/", // the endpoint
        type : "POST", // http method
        data : {
            abvid_serial : window.abvid_serial,
            orig_filename : window.file,
            // This will sub out the mailing list for the email -- but leave backend in place
            pm_email : 'aboutvids@edx.org',
            // Quickest fix/patch (with unpatch avail)
            studio_url : $('#course_url').val(),
            course_name : $("#course_name").val(),
        }, 

        success : function(json) {
            console.log('input_data // sanity check');
        },
        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }
    });
}


/////////////////////////
//                     //
// Crossdomain Handler //
//                     //
/////////////////////////

var allowCrossDomain = function(req, res, next) {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Requested-With, Cache-Control, Accept, Origin, X-Session-ID');
    res.header('Access-Control-Allow-Methods', 'GET,POST,PUT,HEAD,DELETE,TRACE,COPY,LOCK,MKCOL,MOVE,PROPFIND,PROPPATCH,UNLOCK,REPORT,MKACTIVITY,CHECKOUT,MERGE,M-SEARCH,NOTIFY,SUBSCRIBE,UNSUBSCRIBE,PATCH');
    res.header('Access-Control-Allow-Credentials', 'false');
    res.header('Access-Control-Max-Age', '1000');

    next();
};


////////////////////////////////// 
//                              //
//  CSRF HANDLER FOR AJAX CALLS //
//                              //
//////////////////////////////////

function getCookie(name) {
    var cookieValue = null;
    if (document.cookie && document.cookie != '') {
        var cookies = document.cookie.split(';');
        for (var i = 0; i < cookies.length; i++) {
            var cookie = jQuery.trim(cookies[i]);
            // Does this cookie string begin with the name we want?
            if (cookie.substring(0, name.length + 1) == (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}
var csrftoken = getCookie('csrftoken');

/*
The functions below will create a header with csrftoken
*/

function csrfSafeMethod(method) {
    // these HTTP methods do not require CSRF protection
    return (/^(GET|HEAD|OPTIONS|TRACE)$/.test(method));
}
function sameOrigin(url) {
    // test that a given url is a same-origin URL
    // url could be relative or scheme relative or absolute
    var host = document.location.host; // host + port
    var protocol = document.location.protocol;
    var sr_origin = '//' + host;
    var origin = protocol + sr_origin;
    // Allow absolute or scheme relative URLs to same origin
    return (url == origin || url.slice(0, origin.length + 1) == origin + '/') ||
        (url == sr_origin || url.slice(0, sr_origin.length + 1) == sr_origin + '/') ||
        // or any other URL that isn't scheme relative or absolute i.e relative.
        !(/^(\/\/|http:|https:).*/.test(url));
}

$.ajaxSetup({
    beforeSend: function(xhr, settings) {
        if (!csrfSafeMethod(settings.type) && sameOrigin(settings.url)) {
            // Send the token to same-origin, relative URLs only.
            // Send the token only if the method warrants CSRF protection
            // Using the CSRFToken value acquired earlier
            xhr.setRequestHeader("X-CSRFToken", csrftoken);
        }
    }
});
