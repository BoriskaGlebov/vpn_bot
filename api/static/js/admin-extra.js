// Кнопка подтверждения — обычный <button>, поэтому disabled надёжно гасит
// повторный клик быстрее, чем успеет уйти второй параллельный DELETE.
$(document).on('click', '#modal-delete-button', function () {
  $(this).prop('disabled', true);
});

$(document).on('show.bs.modal hidden.bs.modal', '#modal-delete', function () {
  $('#modal-delete-button').prop('disabled', false);
});
