// Handle delete modal
$(document).on('shown.bs.modal', '#modal-delete', function (event) {
  var element = $(event.relatedTarget);

  var name = element.data("name");
  var pk = element.data("pk");
  $("#modal-delete-text").text("This will permanently delete " + name + " " + pk + " ?");

  $("#modal-delete-button").attr("data-url", element.data("url"));
});

$(document).on('click','#modal-delete-button',function() {
  $.ajax({
    url: $(this).attr('data-url'),
    method: 'DELETE',
    success: function(result) {
        window.location.href = result;
    }
  });
});

console.log('Forms query select', document.querySelector('form.list-filter-form'));

$('form.list-filter-form').on('formdata', (e)=> {
  console.log('!!!! onformdata()')
  const formData = e.originalEvent.formData; 
  console.log('Event formData =', formData);
  let ordering = formData.get('o')
  
  const op = formData.get('operand');
  if (op !== undefined && op !== null && op !== ''){
    formData.append(formData.get('full_clause'), op);
  }
  for (key of ['full_clause', 'operand', 'is_active']){
    formData.delete(key)
  }
});

$('form.list-filter-form').on('submit', (e)=> {
  const form = e.target; 
  console.log('!!!! onSubmit()')
  console.log('onSubmit() form=', form);
  const data = Object.fromEntries(new FormData(form).entries());
  console.log('data=',data);
  // return true;
});
