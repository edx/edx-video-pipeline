//////////////////////////
//
// VEDA - AI Form Handling
//
//////////////////////////

var field_list = []
var return_json
var return_data = {}

var tp_speed = {
"extended_service" : "10-Day/Extended",
"default" : "4-Day/Default",
"expedited_service" : "2-Day/Expedited",
"rush_service" : "24 hour/Rush",
"same_day_service" : "Same Day"
};

var c24_speed = {
"STANDARD" : "48h",
"PRIORITY" : "24h"
};

var c24_fidelity = {
"MECHANICAL" : "75%",
"PREMIUM" : "95%",
"PROFESSIONAL" : "99%", 
};


$('#return').hide();
$('#advanced').hide();
$('#data').hide();

// Retrieve INST record
$('#course-form').on('submit', function(event){
    event.preventDefault();
    });


//Let's Change this to a lookup, then send the assoc. code to V.backend
//////////////////////
// Institution List //
//////////////////////
$('#input_text').keyup(function() {
    lookup = $('#input_text').val()
    if (lookup.length > 0) {
        lookup_institution(lookup)
        
    }
    else {
        $('#inst_lookup').empty()
    }
});

function lookup_institution(lookup) {
    $('#inst_lookup').empty()
    var in_ls = window.institution_list
    var i;
    var l;
    for ( i in in_ls ) {
        if (in_ls[i].toLowerCase().indexOf(lookup.toLowerCase()) > -1) {
            $('#inst_lookup').append('<p><span onclick="chooseinst(i=\''+i+'\')">'+in_ls[i]+'</span></p>')
        }
    }
}



function chooseinst(i) {
    $('#initial_title').fadeOut()
    $( ".submit_button" ).each(function() {
        $( this ).attr("style", "background-color: #B2FF00;");
    })
    $('#new-form').fadeOut()
    $('#inst_lookup').empty()
    $('#inst_lookup').fadeOut()
    create_post(inst_code = i);
    $('#advanced').fadeIn();

}


/////////////////////
// NEW INSTITUTION //
/////////////////////
$('#new-form').on('submit', function(event){
    event.preventDefault();
    console.log("new_form submit // sanity check")
    new_institution()
});

function new_institution() {
    $.ajax({
        url : "../new_institution/",
        type : "POST",
        data : {},
        success : function(json) {
            console.log("new form ajax success")
            chooseinst(i='NEWINST')
        },
        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }

    })
}


//////////////////////////////
// ADVANCED SETTINGS TOGGLE //
//////////////////////////////
function adv_toggle() {
    if ($('#advanced_toggle').is(":checked")) { 
        console.log('Checked')
        $('#data').fadeIn();
    }
    else {
        $('#data').fadeOut();
    }
}


////////////////
// RESET FORM //
$('#reset-form').hide();
// Reset Button
$('#reset-form').on('reset', function(event){
    event.preventDefault();
    document.location.reload()
});


/////////////////
// SUBMIT FORM //
/////////////////
$('#submit-form').hide();
$('#submit-form').on('submit', function(event){
    event.preventDefault();
    console.log("final submit // sanity check")
    var submit = check_submit();
    if (submit == true) {
        submit_data();
    }
});


/////////////////////
// Warning Message //
/////////////////////
function create_warning(message) {
    var $warning_div = $("<div>", {
        class: "warning"
    });
    $warning_div.append('<span>'+message+'</span>')
    return $warning_div
}


/////////////////////////
// Edit Fields from AI //
/////////////////////////
var changefield;
var return_json;
var mod_fields = [];

function editField(changefield) {
    generate_field(x=changefield, y=window.return_json['inst_data'][changefield]);

    $('#return_data').empty()
    mod_fields.push(changefield)
    console.log(mod_fields)

    for (i in window.return_json['inst_data']) {
        if (mod_fields.indexOf(i) == -1) {
            $('#return_data').append('<button onclick="editField(changefield=\''+i+'\')">(e)</button>')
            $('#return_data').append('<span>' + return_json['field_data'][i] + ' : \"' + return_json['inst_data'][i] + '\"</span><br>')

        } 
    }
}


/////////////////
// CREATE POST //
/////////////////
function create_post(inst) {
    console.log("create_post // sanity check")
    if (inst != undefined) {
        var inst_code = inst
    }
    else {
        inst_code = 'NEWINST'
    }
    $.ajax({
            url : "../institution_validator/",
            type : "POST",
            data : { 
                input_text : inst_code,
            },

            success : function(json) {
                $("#results").empty()
                $("#institutional").empty();

                var $inst_name = $("<div>", {id: "institution_title", class: "data"});
                $inst_name.append('<span class="tiny_titles">edX Video Pipeline Course Addition Tool : </span><br>')
                if (json.length == 0) {
                    $inst_name.append(('NEW INSTITUTION'));
                }
                else {
                    $inst_name.append((json));
                }

                $("#institutional").append($inst_name);


                var $inst_data = $("<div>", {id: "inst_data", class: "loading"});
                $inst_data.append($loading)
                $("#data").empty();
                $("#data").append($inst_data);
                                
                if (json != 'Error') {

                    // change controls

                    $('#course-form').fadeOut();
                    $('#reset-form').fadeIn();
                    $('#submit-form').fadeIn();

                    $.ajax({
                        url : "../institution_data/",
                        type : "POST",
                        data : { 
                            inst_code : inst_code,
                        },

                        success : function(json) {
                            $("#results").empty()

                            var ready = true;
                            $("#data").empty();
                            var $return_data = $("<div>", {id: "return_data"});

                            return_json = json;
                            return_data['institution'] = inst_code

                            // Generate AI Fields //
                            for (j in json['inst_data']) {

                                $return_data.append('<button onclick="editField(changefield=\''+i+'\')">(e)</button>')
                                $return_data.append('<span>' + json['field_data'][j] + ' : \"' + json['inst_data'][j] + '\"</span><br>')
                                // Add an 'Edit' Field
                                // For Validation on Post
                                return_data[j] = json['inst_data'][j]
                            }
                            // EDX CLASS ID
                            $return_data.append('<button onclick="editField(changefield=\'edx_classid\')">(e)</button>')
                            $return_data.append('<span>edx_classid : \"\"</span><br>')
                            return_data['edx_classid'] = ''
                            //ADD ALL
                            $('#data').append($return_data)
                            appendform();
                        },
                        error : function(xhr,errmsg,err) {
                            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
                        }
                    });
                }
                else{
                    $("#data").empty();
                    $('#data').append('<span>Institution Code Error</span>')
                }
            },
            // handle a non-successful response
            error : function(xhr,errmsg,err) {
                $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
            }
    });

}


// Make the rest of the form appear after form submission
function appendform() {
    if ( typeof ready !== undefined) {
        // $('#course_edit').empty();
        var x
        for (x in window.return_json['field_data']) {
            if (window.return_json['must_haves'][x] != undefined) {
                generate_field(x)
            }
            else {
                if (window.return_json['inst_data'][x] != undefined) {
                    console.log(x + ' : withheld')
                }
                else {
                    if (window.return_json['must_haves'][x] == undefined) {
                        // Transcription Debug
                        if (window.inst_code != 'NEWINST') {
                            if (x.indexOf("c24_") > -1) {

                                if ( x != 'c24_proc' && window.return_json['inst_data']['c24_proc'] != false) {
                                    generate_field(x)
                                }
                                else {
                                    console.log(x + ' : withheld')
                                }
                            }

                            else if (x.indexOf("tp_") > -1) {
                                if (window.return_json["inst_data"]["tp_proc"] == true) {
                                    generate_field(x)
                                }
                                else {
                                    console.log(x + ' : TP withheld')
                                }
                            }
                            else if (x == 'edx_classid') {
                                console.log(x + ' : withheld')
                            }
                        }
                        else {
                            // NEW INSTITUTION
                            generate_field(x)

                            $( "hr" ).each(function() {
                                $( this ).fadeIn()
                            });
                            $('#advanced').fadeOut()
                        }
                    }
                    else { 
                        generate_field(x)
                    }
                }                        
            }
        }
        if (window.inst_code == 'NEWINST') {
            generate_field(x="institution_name")
        }
        $('#course_edit').fadeIn()
    }
}


function generate_field(x, y) {

    if (window.return_json['booleans'][x] != undefined) {
        // Make checkboxes
        var $edit_div = $("<div>", {
            class: "rebox"
        });
        var checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.name = x;
        checkbox.id = x;
        checkbox.checked = false;
        checkbox.value = 'None';
        checkbox.setAttribute("class", "box");

        if (y != undefined) {
            if (y == false) {
                checkbox.checked = false;
            }
            else {
                checkbox.checked = true;
            }
        }

        var label = document.createElement('label')
        label.htmlFor = x;
        label.appendChild(document.createTextNode(return_json['field_data'][x]));
        $edit_div.append(checkbox);
        $edit_div.append(label);
    }

    else if (window.return_json['dropdowns'][x] != undefined) {
        var $edit_div = $("<div>", {
            class: "rebox"
        });
        var html_label = '<span class=\"text_label\">'+return_json['field_data'][x]+'</span>'
        var z;
        var dropdown = document.createElement('select')
        dropdown.setAttribute("id", x)
        dropdown.setAttribute("name", x);
        for (z in window[x]) {
            var op = new Option();
            op.value = z;
            op.text = window[x][z];
            if (y != undefined) {
                if (y == z) {
                    op.setAttribute("selected", "selected");
                }
            }
            dropdown.options.add(op);

        }
        $edit_div.append(html_label);
        $edit_div.append(dropdown);
    }

    else {
        var $edit_div = $("<div>", {
            class: "data_input"
            });
        var textbox = document.createElement("input");
        textbox.setAttribute("type", "text");
        textbox.setAttribute("name", x);
        textbox.setAttribute("id", x);

        if (x == 'edx_classid') {
            textbox.setAttribute("size", 7);
        }
        else if (x == 'institution') {
            textbox.setAttribute("size", 9);
        }
        else {
            textbox.setAttribute("size", 60);
        }
        if (y != undefined) {
            if ( y != "None") {
                textbox.setAttribute("value", y);
            } 
        }
        if (x == 'institution_name') {
            textbox.setAttribute("placeholder", "Institution Name")
        }
        else {
            textbox.setAttribute("placeholder", return_json['field_data'][x])
        }
        $edit_div.append(textbox);
        if (x == 'edx_classid') {
            var $html_span = '<span class=\"advisory\">Can Autogenerate</span>'
            $edit_div.append($html_span)
        }
    }
    if (window.return_json['organizational'][x] != undefined) {
        $('#course_edit_' + window.return_json['organizational'][x]).append($edit_div);
    }
    else {
        $('#course_edit').append($edit_div);
    }
    field_list.push(x)
}


// JS Data validation, warning generation
function check_submit() {
    var submit
    $( ".warning" ).each(function() {
        $( this ).remove()
    })
    // Do basic data checking

    //YES should be here
    if ($('#course_name').val().length < 1) {
        var $add = create_warning(message='Required')
        $('#course_name').parent().append($add)
        $('#course_name').attr("style", "border-color: #FF0000;");
        submit = false
    }
    else {
        $('#course_name').attr("style", "border-color: #7DFF00;");

        // Make Generation field for course code
        if (submit != false) {
            submit = true
        }
    }

    // Youtube Channel (either 24 or none)
    if ($('#yt_channel').val().length != 24 && $('#yt_channel').val().length != 0) {
        var $add = create_warning(message='24 Chars. Req')
        $('#yt_channel').parent().append($add)
        $('#yt_channel').attr("style", "border-color: #FF0000;");
        submit = false
    }
    else {
        if ($('#yt_channel').val().length == 24) {
            $('#yt_channel').attr("style", "border-color: #7DFF00;");
        }
        if (submit != false) {
            submit = true
        }
    }

    // Validate Unique Key
    $.ajax({
        url : "../course_id_validate/",
        type : "POST",
        data : { 
            edx_classid : $('#edx_classid').val(),
            institution : $('#input_text').val(),
        },

        success : function(json) {
            $("#results").empty()
            if (json == true) { 
                $('#edx_classid').attr("style", "border-color: #7DFF00;");
                if (submit != false) {
                    submit = true
                }
            }
            else {
                var $add = create_warning(message='Code Taken')
                $('#edx_classid').parent().append($add)
                $('#edx_classid').attr("style", "border-color: #FF0000;");
                submit = false
            }
        },
        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }
    });

    $('#edx_classid').attr("style", "border-color: #7DFF00;");
    if (submit != false) {
        submit = true
    }

    // VAL URL
    if ($('#local_storedir').val().length < 1) {
        var $add = create_warning(message='Required')
        $('#local_storedir').parent().append($add)
        $('#local_storedir').attr("style", "border-color: #FF0000;");
        submit = false
    }
    else {
        $('#local_storedir').attr("style", "border-color: #7DFF00;");
        if (submit != false) {
            submit = true
        }
    }

    if ($('#institution').val() != undefined) {
        // console.log('NEW INST')
        if ($('#institution').val().length != 3) {
            var $add = create_warning(message='3 Chars. Req')
            $('#institution').parent().append($add)
            $('#institution').attr("style", "border-color: #FF0000;")
            submit = false
        }
        else {
            $.ajax({
                url : "../inst_id_validate/", // the endpoint
                type : "POST", // http method
                data : { 
                // edx_classid : $('#edx_classid').val(),
                    inst_code : $('#institution').val(),
                }, // data sent with the post request

                success : function(json) {
                    // $("#results").empty()
                    console.log('inst_id_validate // sanity check')
                    if (json == '0' ) {
                        // console.log('SUCCESS')
                        submit = true
                        $('#institution').attr("style", "border-color: #7DFF00;");
                    }
                    else {
                        var $add = create_warning(message='Code Taken')
                        $('#institution').parent().append($add)
                        $('#institution').attr("style", "border-color: #FF0000;")
                        submit = false
                    }

                },
                error : function(xhr,errmsg,err) {
                    $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
                }
            });

        }
        if ($('#institution_name').val().length < 1) {
            var $add = create_warning(message='Required')
            $('#institution_name').parent().append($add)
            $('#institution_name').attr("style", "border-color: #FF0000;")
            submit = false
        }
    }
    return submit
}


function submit_data () { 
    var y;
    for ( y in field_list ) {
        if (window.return_json['booleans'][field_list[y]] != undefined) {
            if ($('#'+field_list[y]).is(":checked")) {
                return_data[field_list[y]] = true
            }
            else {
                return_data[field_list[y]] = false
            }
        }
        else {
            return_data[field_list[y]] = $('#'+field_list[y]).val()
        }        
    }

    $.ajax({
        url : "../course_add/",
        type : "POST",
        data : { 
            return_data : JSON.stringify(return_data)
        },
        success : function(json) {
            console.log('Display Results')
            $('#total_input').hide();
            $("#submit-form").hide();
            $("#advanced").hide();

            $('#return').append('<h3>Success!</h3>');
            $('#return').append('<span class=\"advisory\" style=\"margin-left: 49px;\">Paste into edX Studio Advanced Settings > <br>Video Upload Credentials</span>')
            $('#return').append('<span class=\"final_data\"> &nbsp;\"course_video_upload_token\": \"'+json['studio_hex']+'\"&nbsp;<span><br>')
            $('#return').append('<span class=\"advisory\" style=\"margin-left: 49px;\">Pipeline Code : ' + json['course_code'] + '</span><br>')

            // Reset Button
            $('#rstb').attr('value', 'New')
            $('#return').append($('#reset-form'))

            $('#return').fadeIn();
        },

        error : function(xhr,errmsg,err) {
            $('#results').html("<span>SERVER ERROR: "+errmsg+ " : " +err+"</span>");
        }
    });
}


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

